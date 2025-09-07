#!/usr/bin/env python3

"""PL/0 recursive descent parser adapted from Wikipedia"""

from functools import reduce
from copy import deepcopy

import frontend.ast as ast
import ir.ir as ir
from logger import logger, log_indentation, red, green, yellow, magenta, cyan, bold


class Parser:
    def __init__(self, the_lexer):
        self.sym = None
        self.value = None
        self.new_sym = None
        self.new_value = None
        self.the_lexer = the_lexer.tokens()

        # used to mantain scope
        self.current_function = ir.Symbol("main", ir.TYPENAMES['function'])

    def getsym(self):
        """Get next symbol from the lexer"""
        try:
            self.sym = self.new_sym
            self.value = self.new_value
            self.new_sym, self.new_value = next(self.the_lexer)
        except StopIteration:
            return 2
        log_indentation(f"{magenta('Next symbol:')} {self.new_sym} {self.new_value}")
        return 1

    def error(self, msg):
        log_indentation(red(f"{msg} - Current symbol: {self.new_sym} {self.new_value}"))
        raise RuntimeError("Raised error during parsing")

    def accept(self, s):
        accepted_color = red(f"{self.new_sym} == {s}")
        if (self.new_sym == s):
            accepted_color = green(f"{self.new_sym} == {s}")
        log_indentation(f"Trying to accept {accepted_color}")
        return self.getsym() if self.new_sym == s else 0

    def expect(self, s):
        log_indentation(f"{cyan('Expecting:')} {s}")
        if self.accept(s):
            return 1
        self.error("Expect: unexpected symbol")
        return 0

    def array_offset(self, target, symtab):
        offset = None
        idxes = []
        if target.is_array() and self.new_sym == 'lspar':
            for i in range(0, len(target.stype.dims)):
                if self.new_sym != 'lspar':  # we are referencing a subarray
                    break

                self.expect('lspar')
                idxes.append(self.numeric_expression(symtab))
                self.expect('rspar')
            offset = self.linearize_multid_vector(idxes, target, symtab)
        return (offset, len(idxes))

    @staticmethod
    def linearize_multid_vector(explist, target, symtab):
        offset = None
        for i in range(0, len(explist)):
            if i + 1 < len(target.stype.dims):
                planedisp = reduce(lambda x, y: x * y, target.stype.dims[i + 1:])
            else:
                planedisp = 1
            idx = explist[i]
            esize = (target.stype.basetype.size // 8) * planedisp
            planed = ast.BinExpr(children=['times', idx, ast.Const(value=esize, symtab=symtab)], symtab=symtab)
            if offset is None:
                offset = planed
            else:
                offset = ast.BinExpr(children=['plus', offset, planed], symtab=symtab)
        return offset

    @logger
    def factor(self, symtab):
        if self.new_sym == 'ident':
            var = symtab.find(self, self.new_value)
            if not var.is_numeric():
                raise RuntimeError(f"Trying to parse var {var} as numeric when it isn't")

            self.accept('ident')

            offset, num_of_accesses = self.array_offset(var, symtab)
            if offset is None:
                return ast.Var(var=var, symtab=symtab)
            else:
                return ast.ArrayElement(var=var, offset=offset, num_of_accesses=num_of_accesses, symtab=symtab)
        elif self.accept('number'):
            return ast.Const(value=int(self.value), symtab=symtab)
        elif self.accept('lparen'):
            expr = self.algebraic_expression(symtab=symtab)
            self.expect('rparen')
            return expr

        self.error("Factor: syntax error")

    @logger
    def term(self, symtab):
        expr = self.factor(symtab)
        while self.new_sym in ['times', 'slash']:
            self.getsym()
            op = self.sym
            expr2 = self.factor(symtab)
            expr = ast.BinExpr(children=[op, expr, expr2], symtab=symtab)
        return expr

    # XXX: shifts have more precedence than plus/minus, which is maybe wrong, but it's easier to parse negative numbers this way
    @logger
    def shift(self, symtab):
        expr = self.term(symtab)
        while self.new_sym in ['shl', 'shr']:
            self.getsym()
            op = self.sym
            expr2 = self.term(symtab)
            expr = ast.BinExpr(children=[op, expr, expr2], symtab=symtab)
        return expr

    # XXX: weird precedence
    @logger
    def modulus(self, symtab):
        expr = self.shift(symtab)
        if self.new_sym == 'mod':
            self.getsym()
            op = self.sym
            expr2 = self.shift(symtab)
            expr = ast.BinExpr(children=[op, expr, expr2], symtab=symtab)
        return expr

    @logger
    def numeric_expression(self, symtab):
        op = None
        if self.new_sym in ['plus', 'minus']:
            self.getsym()
            op = self.sym
        expr = self.modulus(symtab)
        if op:
            expr = ast.UnExpr(children=[op, expr], symtab=symtab)
        while self.new_sym in ['plus', 'minus']:
            self.getsym()
            op = self.sym
            expr2 = self.modulus(symtab)
            expr = ast.BinExpr(children=[op, expr, expr2], symtab=symtab)
        return expr

    @logger
    def logic_value(self, symtab):
        if self.accept('truesym'):
            return ast.Const(value="True", symtab=symtab)
        elif self.accept('falsesym'):
            return ast.Const(value="False", symtab=symtab)
        elif self.accept('not'):
            return ast.UnExpr(children=['not', self.logic_value(symtab)], symtab=symtab)
        elif self.accept('oddsym'):
            return ast.UnExpr(children=['odd', self.numeric_expression(symtab)], symtab=symtab)
        elif self.accept('lparen'):
            expr = self.logic_expression(symtab=symtab)
            self.expect('rparen')
            return expr
        elif self.new_sym == 'ident':
            var = symtab.find(self, self.new_value)
            if var.is_boolean():
                self.accept('ident')
                offset, num_of_accesses = self.array_offset(var, symtab)
                if offset is None:
                    return ast.Var(var=var, symtab=symtab)
                else:
                    return ast.ArrayElement(var=var, offset=offset, num_of_accesses=num_of_accesses, symtab=symtab)

        expr = self.algebraic_expression(symtab)

        # expr is already a condition
        if isinstance(expr, ast.BinExpr) and expr.children[0] in ast.BINARY_CONDITIONALS:
            return expr

        # if expr is not a condition, it must be a condition
        # otherwise logic_expression == algebraic_expression
        expr = self.condition(expr, symtab)
        return expr

        self.error("Logic value: invalid operator")

    @logger
    def logic_expression(self, symtab):
        expr = self.logic_value(symtab)
        while self.new_sym in ['and', 'or']:
            self.getsym()
            op = self.sym
            expr2 = self.logic_value(symtab)
            expr = ast.BinExpr(children=[op, expr, expr2], symtab=symtab)
        try:
            expr = self.condition(expr, symtab)
        except RuntimeError:
            pass

        return expr

    @logger
    def condition(self, expr, symtab):
        if self.new_sym in ast.BINARY_CONDITIONALS:
            self.getsym()
            op = self.sym
            expr2 = self.algebraic_expression(symtab)
            expr = ast.BinExpr(children=[op, expr, expr2], symtab=symtab)
            return expr
        self.error("Condition: invalid operator")

    @logger
    def algebraic_expression(self, symtab):
        try:
            expr = self.numeric_expression(symtab)
        except RuntimeError:
            expr = self.logic_expression(symtab)

        try:
            expr = self.condition(expr, symtab)
        except RuntimeError:
            pass

        return expr

    @logger
    def string_expression(self, symtab):
        if self.accept('quote'):
            self.accept('string')
            new_string = self.value
            self.accept('quote')
            return ast.String(value=new_string, symtab=symtab)
        elif self.new_sym == 'ident':
            var = symtab.find(self, self.new_value)
            if var.is_string():
                self.accept('ident')
                offset, num_of_accesses = self.array_offset(var, symtab)
                if offset is None:
                    return ast.Var(var=var, symtab=symtab)
                else:
                    return ast.ArrayElement(var=var, offset=offset, num_of_accesses=num_of_accesses, symtab=symtab)

        self.error("Can't parse string expression")

    @logger
    def static_array(self, symtab):
        values = []
        while self.new_sym != 'rspar':
            expr = self.expression(symtab)
            values.append(expr)
            if self.new_sym == "comma":
                self.accept('comma')
                # handle dangling commas e.g. (x, y, )
                if self.new_sym == "rparen":
                    self.error("Wrongly defined arguments for call to function")

        self.accept('rspar')

        self.accept('ident')
        type = self.value
        size = []

        # array of arrays
        while self.accept('lspar'):
            self.expect('number')
            size.append(int(self.value))
            self.expect('rspar')

        if type not in list(ir.TYPENAMES.keys()) or type in ['label', 'function']:
            self.error(f"The type {type} is not valid for an array")

        return ast.StaticArray(values=values, type=ir.TYPENAMES[type], size=size, symtab=symtab)

    @logger
    def expression(self, symtab):
        if self.accept('lspar'):
            return self.static_array(symtab)

        try:
            return self.string_expression(symtab)
        except RuntimeError:
            pass

        return self.algebraic_expression(symtab)

    @logger
    def statement(self, symtab):
        if self.accept('beginsym'):
            statement_list = ir.StatList(symtab=symtab)

            statement_list.append(self.statement(symtab))
            while self.accept('semicolon'):
                statement_list.append(self.statement(symtab))

            self.expect('endsym')
            log_indentation(f"{bold(statement_list.get_content())}")
            return statement_list

        elif self.accept('ident'):
            target = symtab.find(self, self.value)
            offset, num_of_accesses = self.array_offset(target, symtab)

            if self.accept('incsym'):
                if not target.is_numeric():
                    self.error("Trying to increment a non numeric variable")

                if offset is None:
                    dest = ast.Var(var=target, symtab=symtab)
                else:
                    dest = ast.ArrayElement(var=target, offset=deepcopy(offset), num_of_accesses=num_of_accesses, symtab=symtab)
                expr = ast.BinExpr(children=['plus', dest, ast.Const(value=1, symtab=symtab)], symtab=symtab)
            else:
                self.expect('becomes')
                expr = self.expression(symtab)

            return ast.AssignStat(target=target, offset=offset, expr=expr, symtab=symtab)

        elif self.accept('callsym'):
            self.expect('ident')
            function_symbol = symtab.find(self, self.value)
            self.expect('lparen')

            # parameters
            parameters = []
            while self.new_sym != "rparen":
                expr = self.expression(symtab)
                parameters.append(expr)
                if self.new_sym == "comma":
                    self.accept('comma')
                    # handle dangling commas e.g. (x, y, )
                    if self.new_sym == "rparen":
                        self.error("Wrongly defined arguments for call to function")

            self.expect("rparen")

            # return
            returns = []
            if self.new_sym == "returns":
                self.accept('returns')
                self.expect('lparen')

                while self.new_sym != "rparen":
                    if self.new_sym == "dontcaresym":
                        self.accept('dontcaresym')
                        returns.append(("_", None))
                    else:
                        self.accept('ident')
                        var = symtab.find(self, self.value)
                        offset, num_of_accesses = self.array_offset(var, symtab)
                        returns.append((var, offset))

                    if self.new_sym == "comma":
                        self.accept('comma')
                        # handle dangling commas e.g. (x, y, )
                        if self.new_sym == "rparen":
                            self.error("Wrongly defined returns for call to function")

                self.expect("rparen")

            return ast.CallStat(function_symbol=function_symbol, parameters=parameters, returns=returns, symtab=symtab)

        elif self.accept('ifsym'):
            cond = self.logic_expression(symtab)
            self.expect('thensym')
            then = self.statement(symtab)

            elifs = ir.StatList(symtab=symtab)  # TODO: this should be a normal list
            while self.new_sym == "elifsym":
                self.accept("elifsym")
                elif_cond = self.logic_expression(symtab)
                elifs.append(elif_cond)

                self.expect('thensym')
                elif_then = self.statement(symtab)
                elifs.append(elif_then)

            els = None
            if self.accept('elsesym'):
                els = self.statement(symtab)
            return ast.IfStat(cond=cond, thenpart=then, elifspart=elifs, elsepart=els, symtab=symtab)

        elif self.accept('whilesym'):
            cond = self.logic_expression(symtab)
            self.expect('dosym')
            body = self.statement(symtab)
            return ast.WhileStat(cond=cond, body=body, symtab=symtab)

        elif self.accept('forsym'):
            log_indentation(yellow("First part of for statement"))
            # check that there is an assign statement
            if self.new_sym != "ident":
                self.error("First part of for statement must be assignment")
            init = self.statement(symtab)

            self.expect('semicolon')

            log_indentation(yellow("Second part of for statement"))
            cond = self.logic_expression(symtab)

            self.expect('semicolon')

            log_indentation(yellow("Third part of for statement"))
            # check that there is an assign statement
            if self.new_sym != "ident":
                self.error("Third part of for statement must be assignment")
            step = self.statement(symtab)

            self.expect('dosym')
            body = self.statement(symtab)
            return ast.ForStat(init=init, cond=cond, step=step, body=body, symtab=symtab)

        elif self.accept('print'):
            expr = self.expression(symtab)
            return ast.PrintStat(expr=expr, symtab=symtab)

        elif self.accept('read'):
            self.expect('ident')
            target = symtab.find(self, self.value)
            offset, num_of_accesses = self.array_offset(var, symtab)
            return ast.AssignStat(target=target, offset=offset, expr=ast.ReadStat(symtab=symtab), symtab=symtab)

        elif self.accept('returnsym'):
            self.expect('lparen')

            returns = []
            while self.new_sym != "rparen":
                expr = self.expression(symtab)
                returns.append(expr)
                if self.new_sym == "comma":
                    self.accept('comma')
                    # handle dangling commas e.g. (x, y, )
                    if self.new_sym == "rparen":
                        self.error("Wrongly defined return")

            self.expect('rparen')

            return ast.ReturnStat(children=returns, symtab=symtab)

    @logger
    def block(self, parent_symtab, local_symtab, alloct='auto'):
        # variables definition
        while self.accept('constsym') or self.accept('varsym'):
            if self.sym == 'constsym':
                self.constdef(local_symtab, alloct)
                while self.accept('comma'):
                    self.constdef(local_symtab, alloct)
            else:
                # get all the newly defined symbols
                new_symbols = []
                new_symbols.append(self.vardef(alloct))
                while self.accept('comma'):
                    new_symbols.append(self.vardef(alloct))

                # get the type of the new symbols
                if not self.accept('colon'):
                    self.error("Some variables were defined without explicit types")

                self.accept('ident')

                if self.value not in list(ir.TYPENAMES.keys()) or self.value in ['label', 'function']:
                    self.error(f"The type {self.value} is not valid for a variable")

                type = ir.TYPENAMES[self.value]

                # set the types for the new symbols and add them to the symtab
                for new_symbol in new_symbols:
                    if new_symbol.stype is None:
                        new_symbol.stype = type
                    elif isinstance(new_symbol.stype, ir.ArrayType):
                        size = new_symbol.stype.dims
                        new_symbol.stype = ir.ArrayType(None, size, type)
                    local_symtab.push(new_symbol)
                    log_indentation(f"{green('Parsed variable:')} {str(new_symbol)}")

                self.expect('semicolon')

        log_indentation(green("Parsed variables definition"))

        # functions definition
        function_defs = ir.DefinitionList()

        while self.accept('procsym'):
            self.expect('ident')
            fname = self.value
            function_symbol = ir.Symbol(fname, ir.TYPENAMES['function'])
            local_symtab.push(function_symbol)
            procedure_symtab = ir.SymbolTable()

            # save the current function and restore it after parsing this new one
            parent_function = self.current_function
            self.current_function = function_symbol

            self.expect('lparen')

            # parameters
            parameters = []
            while self.new_sym != "rparen":
                new_parameters = []
                new_parameters.append(self.vardef('param'))
                while self.accept('comma'):
                    new_parameters.append(self.vardef('param'))

                # get the type of the parameters
                if not self.accept('colon'):
                    self.error("Some parameters were defined without explicit types")

                self.accept('ident')

                if self.value not in list(ir.TYPENAMES.keys()) or self.value in ['label', 'function']:
                    self.error(f"Type {self.value} is not valid")

                type = ir.TYPENAMES[self.value]

                # set the types for the new parameters and add them to the rest of the parameters
                for new_parameter in new_parameters:
                    if new_parameter.stype is None:
                        new_parameter.stype = type
                    elif isinstance(new_parameter.stype, ir.ArrayType):
                        size = new_parameter.stype.dims
                        new_parameter.stype = ir.ArrayType(None, size, type)

                parameters += new_parameters

                # next batch of parameters with the same type
                if self.new_sym == 'comma':
                    self.accept('comma')

            self.expect('rparen')

            for i in range(len(parameters)):
                # reversed in the symtab for easier datalayout
                procedure_symtab.append(parameters[len(parameters) - i - 1])

            # if the function returns something - it's not mandatory
            returns = []
            if self.new_sym == "returns":
                self.accept('returns')
                self.expect('lparen')

                while self.new_sym != "rparen":
                    self.expect('ident')
                    type = self.value
                    size = []

                    # array
                    while self.accept('lspar'):
                        self.expect('number')
                        size.append(int(self.value))
                        self.expect('rspar')

                    if type not in list(ir.TYPENAMES.keys()) or type in ['label', 'function']:
                        self.error(f"Type {type} is not valid")

                    # XXX: this symbols are only used for their type and size, they are
                    #      not in any SymbolTable and cannot be referenced in the program
                    if len(size) > 0:
                        ret = ir.Symbol(f"ret_{str(len(returns))}_{fname}", ir.ArrayType(None, size, ir.TYPENAMES[type]), alloct='return', function_symbol=function_symbol)
                    else:
                        ret = ir.Symbol(f"ret_{str(len(returns))}_{fname}", ir.TYPENAMES[type], alloct='return', function_symbol=function_symbol)
                    returns.append(ret)

                    if self.new_sym == "comma":
                        self.accept('comma')
                        # handle dangling commas e.g. (int, int, )
                        if self.new_sym == "rparen":
                            self.error("Dangling comma in returns definition")

                self.expect('rparen')

            self.expect('semicolon')

            procedure_symtab = ir.SymbolTable(procedure_symtab + local_symtab)
            fbody = self.block(local_symtab, procedure_symtab)

            # restore parent_function
            self.current_function = parent_function

            self.expect('semicolon')
            function_defs.append(ir.FunctionDef(symbol=function_symbol, parameters=parameters, body=fbody, returns=returns))

        log_indentation(green("Parsed functions definition"))

        # parse the block statements
        statements = self.statement(local_symtab)
        return ir.Block(gl_sym=parent_symtab, lc_sym=local_symtab, defs=function_defs, body=statements)

    @logger
    def constdef(self, local_vars, alloct='auto'):
        self.expect('ident')
        name = self.value
        self.expect('eql')
        self.expect('number')
        local_vars.append(ir.Symbol(name, ir.TYPENAMES['int'], alloct=alloct, function_symbol=self.current_function), int(self.value))
        while self.accept('comma'):
            self.expect('ident')
            name = self.value
            self.expect('eql')
            self.expect('number')
            local_vars.append(ir.Symbol(name, ir.TYPENAMES['int'], alloct=alloct, function_symbol=self.current_function), int(self.value))

    @logger
    def vardef(self, alloct='auto'):
        self.expect('ident')
        name = self.value
        size = []

        # array
        while self.accept('lspar'):
            self.expect('number')
            size.append(int(self.value))
            self.expect('rspar')

        new_var = ''

        # XXX: do not assign the types yet
        if len(size) > 0:
            new_var = ir.Symbol(name, ir.ArrayType(None, size, None), alloct=alloct, function_symbol=self.current_function)
        else:
            new_var = ir.Symbol(name, None, alloct=alloct, function_symbol=self.current_function)

        return new_var

    @logger
    def program(self):
        """Axiom"""
        # for the main, this acts also as the local_symtab
        global_symtab = ir.SymbolTable()
        self.getsym()
        the_program = self.block(global_symtab, global_symtab, alloct='global')
        self.expect('period')
        return the_program
