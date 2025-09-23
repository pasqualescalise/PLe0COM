#!/usr/bin/env python3

"""PL/0 recursive descent parser adapted from Wikipedia"""

from functools import reduce
from copy import deepcopy

import frontend.ast as ast
import ir.ir as ir
from logger import logger, log_indentation, red, green, yellow, magenta, cyan, bold

LOGICAL_OPERATORS = ['and', 'or']
CONDITION_OPERATORS = ['eql', 'neq', 'lss', 'leq', 'gtr', 'geq']
ADDITIVE_OPERATORS = ['plus', 'minus']
MULTIPLICATIVE_OPERATORS = ['times', 'slash', 'mod', 'shl', 'shr']

UNARY_OPERATORS = ['plus', 'minus', 'not', 'odd']  # XXX: no increment/decrement


class Parser:
    def __init__(self, lexer):
        self.sym = None
        self.value = None
        self.new_sym = None
        self.new_value = None
        self.lexer = lexer
        self.tokens = lexer.tokens()

        # used to mantain scope
        self.current_function = ir.Symbol("main", ir.TYPENAMES['function'])

    def getsym(self):
        """Get next symbol from the lexer"""
        try:
            self.sym = self.new_sym
            self.value = self.new_value
            self.new_sym, self.new_value = next(self.tokens)
        except StopIteration:
            return 2
        log_indentation(f"{magenta('Next symbol:')} {self.new_sym} {self.new_value}")
        return 1

    def error(self, msg):
        line = self.lexer.line_number
        raise RuntimeError(red(f"Parsing error at line {line} - {msg} - Current symbol: {self.new_sym} {self.new_value}"))

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

    def type(self):
        self.expect('ident')

        assignable_types = [x for x in ir.TYPENAMES if 'assignable' in ir.TYPENAMES[x].qualifiers]

        if self.value in assignable_types or self.value == "char":
            basetype = ir.TYPENAMES[self.value]

        dims = []
        while self.accept('lspar'):
            self.expect('number')
            dims.append(int(self.value))
            self.expect('rspar')

        if dims == []:
            if basetype == ir.TYPENAMES['char']:
                self.error("Can't use a variable of type char, only type char[]")
            return basetype

        return ir.ArrayType(None, dims, basetype)

    def array_offset(self, target, symtab):
        offset = None
        idxes = []
        if target.is_array() and self.new_sym == 'lspar':
            for i in range(0, len(target.type.dims)):
                if self.new_sym != 'lspar':  # we are referencing a subarray
                    break

                self.expect('lspar')
                idxes.append(self.expression(symtab))
                self.expect('rspar')
            offset = self.linearize_multid_vector(idxes, target, symtab)
        return (offset, len(idxes))

    @staticmethod
    def linearize_multid_vector(explist, target, symtab):
        offset = None
        for i in range(0, len(explist)):
            if i + 1 < len(target.type.dims):
                planedisp = reduce(lambda x, y: x * y, target.type.dims[i + 1:])
            else:
                planedisp = 1
            idx = explist[i]
            esize = (target.type.basetype.size // 8) * planedisp
            planed = ast.BinaryExpr(children=['times', idx, ast.Const(value=esize, symtab=symtab)], symtab=symtab)
            if offset is None:
                offset = planed
            else:
                offset = ast.BinaryExpr(children=['plus', offset, planed], symtab=symtab)
        return offset

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
                    self.error("Wrongly defined values of static array")

        self.accept('rspar')

        values_type = self.type()

        return ast.StaticArray(values=values, values_type=values_type, symtab=symtab)

    # EXPRESSIONS

    @logger
    def expression(self, symtab):
        return self.logical(symtab)

    @logger
    def logical(self, symtab):
        expr = self.condition(symtab)

        while self.new_sym in LOGICAL_OPERATORS:
            self.getsym()
            operator = self.sym
            expr2 = self.condition(symtab)
            expr = ast.BinaryExpr(children=[operator, expr, expr2], symtab=symtab)

        return expr

    @logger
    def condition(self, symtab):
        expr = self.additive(symtab)

        while self.new_sym in CONDITION_OPERATORS:
            self.getsym()
            operator = self.sym
            expr2 = self.additive(symtab)
            expr = ast.BinaryExpr(children=[operator, expr, expr2], symtab=symtab)

        return expr

    @logger
    def additive(self, symtab):
        expr = self.multiplicative(symtab)

        while self.new_sym in ADDITIVE_OPERATORS:
            self.getsym()
            operator = self.sym
            expr2 = self.multiplicative(symtab)
            expr = ast.BinaryExpr(children=[operator, expr, expr2], symtab=symtab)

        return expr

    @logger
    def multiplicative(self, symtab):
        expr = self.unary_expression(symtab)

        while self.new_sym in MULTIPLICATIVE_OPERATORS:
            self.getsym()
            operator = self.sym
            expr2 = self.unary_expression(symtab)
            expr = ast.BinaryExpr(children=[operator, expr, expr2], symtab=symtab)

        return expr

    @logger
    def unary_expression(self, symtab):
        unary_operators = []
        while self.new_sym in UNARY_OPERATORS:
            self.getsym()
            unary_operators += [self.sym]

        expr = self.primary(symtab)

        for operator in list(reversed(unary_operators)):
            expr = ast.UnaryExpr(children=[operator, expr], symtab=symtab)

        while self.accept('incsym') or self.accept('decsym'):
            expr = ast.BinaryExpr(children=['plus' if self.sym == 'incsym' else 'minus', expr, ast.Const(value=1, symtab=symtab)], symtab=symtab)

        return expr

    @logger
    def primary(self, symtab):
        if self.accept('ident'):
            var = symtab.find(self, self.value)

            offset, num_of_accesses = self.array_offset(var, symtab)
            if offset is None:
                return ast.Var(var=var, symtab=symtab)
            else:
                return ast.ArrayElement(var=var, offset=offset, num_of_accesses=num_of_accesses, symtab=symtab)

        elif self.accept('number'):
            return ast.Const(value=int(self.value), symtab=symtab)

        elif self.accept('quote'):
            self.accept('string')
            new_string = self.value
            self.accept('quote')
            return ast.String(value=new_string, symtab=symtab)

        elif self.accept('truesym'):
            return ast.Const(value="True", symtab=symtab)
        elif self.accept('falsesym'):
            return ast.Const(value="False", symtab=symtab)

        elif self.accept('lspar'):
            static_array = self.static_array(symtab)
            # TODO: add a way to directly index the static array
            return static_array

        elif self.accept('lparen'):
            expr = self.expression(symtab=symtab)
            self.expect('rparen')
            return expr

        self.error("Can't accept {self.sym} as primary symbol")

    # STATEMENTS

    @logger
    def statement(self, symtab):
        if self.accept('beginsym'):
            statement_list = ast.StatList(symtab=symtab)

            statement_list.append(self.statement(symtab))
            while self.accept('semicolon'):
                statement_list.append(self.statement(symtab))

            self.expect('endsym')
            log_indentation(f"{bold(statement_list.get_content())}")
            return statement_list

        elif self.accept('ident'):
            target = symtab.find(self, self.value)
            offset, num_of_accesses = self.array_offset(target, symtab)

            if self.accept('incsym') or self.accept('decsym'):
                if offset is None:
                    dest = ast.Var(var=target, symtab=symtab)
                else:
                    dest = ast.ArrayElement(var=target, offset=deepcopy(offset), num_of_accesses=num_of_accesses, symtab=symtab)
                expr = ast.BinaryExpr(children=['plus' if self.sym == 'incsym' else 'minus', dest, ast.Const(value=1, symtab=symtab)], symtab=symtab)
            else:
                self.expect('becomes')
                expr = self.expression(symtab)

            return ast.AssignStat(target=target, offset=offset, expr=expr, num_of_accesses=num_of_accesses, symtab=symtab)

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
                        returns.append((var, offset, num_of_accesses))

                    if self.new_sym == "comma":
                        self.accept('comma')
                        # handle dangling commas e.g. (x, y, )
                        if self.new_sym == "rparen":
                            self.error("Wrongly defined returns for call to function")

                self.expect("rparen")

            return ast.CallStat(function_symbol=function_symbol, parameters=parameters, returns=returns, symtab=symtab)

        elif self.accept('ifsym'):
            cond = self.expression(symtab)
            self.expect('thensym')
            then = self.statement(symtab)

            elifs = ast.StatList(symtab=symtab)
            elifs_conditions = []  # this can't go in the StatList since they are not Stats
            while self.new_sym == "elifsym":
                self.accept("elifsym")
                elif_cond = self.expression(symtab)
                elifs_conditions.append(elif_cond)

                self.expect('thensym')
                elif_then = self.statement(symtab)
                elifs.append(elif_then)

            els = None
            if self.accept('elsesym'):
                els = self.statement(symtab)
            return ast.IfStat(cond=cond, thenpart=then, elifspart=elifs, elifs_conditions=elifs_conditions, elsepart=els, symtab=symtab)

        elif self.accept('whilesym'):
            cond = self.expression(symtab)
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
            cond = self.expression(symtab)

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
            return ast.AssignStat(target=target, offset=offset, num_of_accesses=num_of_accesses, expr=ast.ReadStat(symtab=symtab), symtab=symtab)

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
                # get all the newly defined variables and add them to the symtab

                new_symbols = self.varsdef(alloct)

                for new_symbol in new_symbols:
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
                parameters += self.varsdef('param')

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
                    type = self.type()

                    # XXX: this symbols are only used for their type and size, they are
                    #      not in any SymbolTable and cannot be referenced in the program
                    ret = ir.Symbol(f"ret_{str(len(returns))}_{fname}", type, alloct='return', function_symbol=function_symbol)
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
    def constdef(self, local_vars, alloct='auto'):  # TODO: unused at the moment
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
    def varsdef(self, alloct='auto'):
        new_vars = []

        self.expect('ident')
        new_vars.append(self.value)
        while self.accept('comma'):
            self.expect('ident')
            new_vars.append(self.value)

        # get the type of the new symbols
        if not self.accept('colon'):
            self.error("Some variables were defined without explicit types")

        type = self.type()

        new_symbols = []

        # set the types for the new symbols
        for new_var in new_vars:
            new_symbols.append(ir.Symbol(new_var, type, alloct=alloct, function_symbol=self.current_function))

        return new_symbols

    @logger
    def program(self):
        """Axiom"""
        # for the main, this acts also as the local_symtab
        global_symtab = ir.SymbolTable()
        self.getsym()
        main_body = self.block(global_symtab, global_symtab, alloct='global')
        main = ir.FunctionDef(symbol=self.current_function, parameters=[], body=main_body, returns=[], called_by_counter=1)
        self.expect('end of file')
        return main
