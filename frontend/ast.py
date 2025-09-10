#!/usr/bin/env python3

"""Abstract Syntax Tree

Representation of the source code as a tree, created by the parser. Nodes
represent variables, expressions or statements.
Each node has to implement the following methods:
    + lower, to convert itself into a Statement List of IR statements; all
      of these StatLists are successively flattened
    + __deepcopy__, specifying a method to copy them and their attributes
"""

from copy import deepcopy
from math import log

from ir.function_tree import FunctionTree
import ir.ir as ir
from logger import log_indentation, ii, magenta, cyan, bold
import logger


# UTILITIES

UNARY_CONDITIONALS = ['odd']
BINARY_CONDITIONALS = ['eql', 'neq', 'lss', 'leq', 'gtr', 'geq']


# Returns statements that mask shorts and bytes, to eliminate sign extension
def mask_numeric(operand, symtab):
    mask = [int(0x000000ff), int(0x0000ffff)][operand.stype.size // 8 - 1]  # either byte or short
    mask_temp = ir.new_temporary(symtab, ir.TYPENAMES['int'])
    load_mask = ir.LoadImmStat(dest=mask_temp, val=mask, symtab=symtab)
    apply_mask = ir.BinStat(dest=operand, op="and", srca=operand, srcb=load_mask.destination(), symtab=symtab)
    return [load_mask, apply_mask]


# ASTNODE

class ASTNode:  # abstract
    def __init__(self, parent=None, children=None, symtab=None):
        self.symtab = symtab
        self.parent = parent
        if children:
            self.children = children[:]
            for c in self.children:
                try:
                    c.parent = self
                except Exception:
                    # TODO: error checking
                    pass
        else:
            self.children = []

    # XXX: must only be used for printing
    def type(self):
        return ".".join(str(type(self)).split("'")[1].split(".")[-2:])

    def __repr__(self):
        try:
            # TODO: print this better (a non-empty statement with a label)
            label = f"{magenta(f'{self.get_label().name}')}: "
        except AttributeError:
            label = ''

        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'local_symtab', 'offset', 'function_symbol', 'parameters', 'returns', 'called_by_counter', 'epilogue', 'values'} & set(dir(self))

        res = f"{cyan(f'{self.type()}')}, {id(self)}" + " {"
        if self.parent is not None:
            # res += f"\nparent: {id(self.parent)};\n"
            res += "\n"

        res = f"{label}{res}"

        if "children" in dir(self) and len(self.children):
            res += ii("children: {\n")
            for child in self.children:
                rep = repr(child).split("\n")
                res += "\n".join([f"{' ' * 8}{s}" for s in rep])
                res += "\n"
            res += ii("}\n")

        for attr in attrs:
            node = getattr(self, attr)
            rep = repr(node).split("\n")
            if len(rep) > 1:
                reps = "\n".join([f"{' ' * 8}" + s for s in rep[1:]])
                rep = f"{rep[0]}\n{reps}"
            else:
                rep = f"{rep[0]}"
            res += ii(f"{cyan(f'{attr}')} {bold('->')} {rep}\n")

        res += "}"
        return res

    def navigate(self, action, *args, quiet=False):
        attrs = ['defs', 'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'global_symtab', 'local_symtab', 'offset', 'epilogue']
        attrs = [x for x in attrs if x in set(dir(self))]

        if 'children' in dir(self) and len(self.children):
            if not quiet:
                log_indentation(f"Navigating to {cyan(len(self.children))} children of {cyan(self.type())}, {id(self)}")
            for node in self.children:
                try:
                    logger.indentation += 1
                    node.navigate(action, *args, quiet=quiet)
                    logger.indentation -= 1
                except AttributeError:
                    logger.indentation -= 1

        for attr in attrs:
            try:
                if not quiet:
                    log_indentation(f"Navigating to attribute {cyan(attr)} of {cyan(self.type())}, {id(self)}")
                logger.indentation += 1
                node = getattr(self, attr)
                node.navigate(action, *args, quiet=quiet)
                logger.indentation -= 1
            except AttributeError:
                logger.indentation -= 1
        if not quiet:
            log_indentation(f"Navigating to {cyan(self.type())}, {id(self)}")

        # XXX: shitty solution
        try:
            action(self, *args)
        except TypeError:
            action(self)

    def replace(self, old, new):
        new.parent = self
        if 'children' in dir(self) and len(self.children) and old in self.children:
            self.children[self.children.index(old)] = new
            return True
        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'global_symtab', 'local_symtab', 'offset', 'epilogue'} & set(dir(self))

        for d in attrs:
            try:
                if getattr(self, d) == old:
                    setattr(self, d, new)
                    return True
            except AttributeError:
                pass
        return False

    def get_function(self):
        if not self.parent:
            return self
        elif isinstance(self.parent, ir.FunctionDef):
            return self.parent
        else:
            return self.parent.get_function()


# CONST and VAR

class Const(ASTNode):
    def __init__(self, parent=None, value=0, symbol=None, symtab=None):
        log_indentation(bold(f"New Const Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value
        self.symbol = symbol

    def lower(self):  # TODO: make it possible to define constant booleans
        if self.value in ["True", "False"]:
            new = ir.new_temporary(self.symtab, ir.TYPENAMES['boolean'])
            loadst = ir.LoadImmStat(dest=new, val=self.value, symtab=self.symtab)
        elif self.symbol is None:
            new = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            loadst = ir.LoadImmStat(dest=new, val=self.value, symtab=self.symtab)
        else:
            new = ir.new_temporary(self.symtab, self.symbol.stype)
            loadst = ir.LoadStat(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, ir.StatList(children=[loadst], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return Const(parent=self.parent, value=self.value, symbol=self.symbol, symtab=self.symtab)


class Var(ASTNode):
    """loads in a temporary the value pointed to by the symbol"""

    def __init__(self, parent=None, var=None, symtab=None):
        log_indentation(bold(f"New Var Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.symbol = var

    def lower(self):
        if self.symbol.is_string() and self.symbol.alloct != 'param':  # load strings as char pointers
            ptrreg = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.stype.basetype))
            loadptr = ir.LoadPtrToSym(dest=ptrreg, symbol=self.symbol, symtab=self.symtab)
            return self.parent.replace(self, ir.StatList(children=[loadptr], symtab=self.symtab))

        elif self.symbol.is_array() and self.symbol.alloct != 'param':  # load arrays as pointers
            ptrreg = ir.new_temporary(self.symtab, ir.PointerType(ir.PointerType(self.symbol.stype.basetype)))
            loadptr = ir.LoadPtrToSym(dest=ptrreg, symbol=self.symbol, symtab=self.symtab)
            return self.parent.replace(self, ir.StatList(children=[loadptr], symtab=self.symtab))

        new = ir.new_temporary(self.symtab, self.symbol.stype)
        loadst = ir.LoadStat(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, ir.StatList(children=[loadst], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return Var(parent=self.parent, var=self.symbol, symtab=self.symtab)


class ArrayElement(ASTNode):
    """loads in a temporary the value pointed by: the symbol + the index"""

    def __init__(self, parent=None, var=None, offset=None, num_of_accesses=0, symtab=None):
        """offset can NOT be a list of exps in case of multi-d arrays; it should
        have already been flattened beforehand"""
        log_indentation(bold(f"New ArrayElement Node (id: {id(self)})"))
        super().__init__(parent, [offset], symtab)
        self.symbol = var
        self.offset = offset
        # for a multidimensional array, how deep is this element
        self.num_of_accesses = num_of_accesses

    def lower(self):
        src = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.stype.basetype))
        dest = ir.new_temporary(self.symtab, self.symbol.stype.basetype)
        off = self.offset.destination()

        # at compile time, the dimensions of the array are always 0; we correct
        # this by getting the symbol that contains the real dynamic size of the
        # dimensions and substituiting the constant "0" with this symbol
        if self.symbol.alloct == 'heap':
            dynamic_sizes = self.symbol.dynamic_sizes
            i = 0
            for child in self.offset.children:
                if len(child.children) < 2:
                    continue

                size_statement = child.children[1].children[0]
                correct_size_statement = ir.LoadStat(dest=size_statement.dest, symbol=dynamic_sizes[i], symtab=size_statement.symtab)
                child.children[1].replace(size_statement, correct_size_statement)

                i += 1

        statl = [self.offset]

        if self.symbol.alloct == 'param':
            # pass by reference, we have to deallocate the pointer twice
            parameter = ir.new_temporary(self.symtab, ir.PointerType(ir.PointerType(self.symbol.stype.basetype)))
            loadparameter = ir.LoadPtrToSym(dest=parameter, symbol=self.symbol, symtab=self.symtab)

            array_pointer = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.stype.basetype))
            loadptr = ir.LoadStat(dest=array_pointer, symbol=parameter, symtab=self.symtab)
            statl += [loadparameter, loadptr]
        else:
            array_pointer = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.stype.basetype))
            loadptr = ir.LoadPtrToSym(dest=array_pointer, symbol=self.symbol, symtab=self.symtab)

            statl += [loadptr]

        add = ir.BinStat(dest=src, op='plus', srca=array_pointer, srcb=off, symtab=self.symtab)
        statl += [add]

        if self.symbol.is_monodimensional_array() or (not self.symbol.is_monodimensional_array() and not self.symbol.is_string()):
            statl += [ir.LoadStat(dest=dest, symbol=src, symtab=self.symtab)]

        return self.parent.replace(self, ir.StatList(children=statl, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_offset = deepcopy(self.offset, memo)
        return ArrayElement(parent=self.parent, var=self.symbol, offset=new_offset, symtab=self.symtab)


class String(ASTNode):
    """Puts a fixed string in the data SymbolTable"""

    def __init__(self, parent=None, value="", symtab=None):
        log_indentation(bold(f"New String Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value

    def lower(self):
        # put the string in the data SymbolTable
        data_variable = ir.DataSymbolTable.add_data_symbol(ir.ArrayType(None, [len(self.value) + 1], ir.TYPENAMES['char']), value=self.value)

        # load the fixed data string address
        ptrreg_data = ir.new_temporary(self.symtab, ir.PointerType(data_variable.stype.basetype))
        access_string = ir.LoadPtrToSym(dest=ptrreg_data, symbol=data_variable, symtab=self.symtab)

        return self.parent.replace(self, ir.StatList(children=[access_string], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return String(parent=self.parent, value=self.value, symtab=self.symtab)


class StaticArray(ASTNode):
    # XXX: this doesn't get lowered, other nodes expand themselves and
    #      access the array values one by one

    def __init__(self, parent=None, values=[], type=None, size=[], symtab=None):
        log_indentation(bold(f"New StaticArray Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.values_type = type
        self.values = values
        for value in self.values:
            value.parent = self

        if size != []:
            self.values_type = ir.ArrayType(None, size, type)
        self.size = size  # we need this for the deepcopy

    def __deepcopy__(self, memo):
        new_values = []
        for value in self.values:
            new_values.append(deepcopy(value, memo))

        return StaticArray(parent=self.parent, values=new_values, type=self.values_type, size=self.size, symtab=self.symtab)

    # TODO: definitely needs type checking, also stuff like String length


# EXPRESSIONS

class Expr(ASTNode):  # abstract
    def get_operator(self):
        return self.children[0]


class BinExpr(Expr):
    def __init__(self, parent=None, children=None, symtab=None):
        log_indentation(bold(f"New BinExpr Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)

    def lower(self):
        stats = [self.children[1], self.children[2]]

        srca = self.children[1].destination()
        srcb = self.children[2].destination()

        # type checking
        if srca.stype.name == srcb.stype.name:
            desttype = ir.TYPENAMES[srca.stype.name]
        elif srca.stype.is_numeric() and srcb.stype.is_numeric():  # apply a mask to the smallest operand
            smallest_operand = srca if srca.stype.size < srcb.stype.size else srcb
            biggest_operand = srca if srca.stype.size > srcb.stype.size else srcb
            stats += mask_numeric(smallest_operand, self.symtab)
            desttype = ir.Type(biggest_operand.stype.name, biggest_operand.stype.size, 'Int')
        else:
            raise RuntimeError(f"Trying to operate on two factors of different types ({srca.stype.name} and {srcb.stype.name})")

        if ('unsigned' in srca.stype.qualifiers) and ('unsigned' in srcb.stype.qualifiers):
            desttype.qualifiers += ['unsigned']

        if self.children[0] in BINARY_CONDITIONALS:
            dest = ir.new_temporary(self.symtab, ir.TYPENAMES['boolean'])
        else:
            dest = ir.new_temporary(self.symtab, desttype)

        if self.children[0] not in ["slash", "mod"]:
            stmt = ir.BinStat(dest=dest, op=self.children[0], srca=srca, srcb=srcb, symtab=self.symtab)
            stats += [stmt]
            return self.parent.replace(self, ir.StatList(children=stats, symtab=self.symtab))

        elif self.children[0] == "mod":
            """
            try to see at compile time if the dividend of
            the modulus is a power of two:

            + if it is, there is a codegen implementation
            + if we don't know, implement the modulus as a while loop
              so that `res = op1 % op2`
              becomes something like

              while (op1 >= op2) {
                  op1 = op1 - op2;
              }
              res = op1;
            """
            if isinstance(self.children[2].children[0], ir.LoadImmStat) and log(self.children[2].children[0].val, 2).is_integer():
                stmt = ir.BinStat(dest=dest, op="mod", srca=srca, srcb=srcb, symtab=self.symtab)
                stats += [stmt]
                return self.parent.replace(self, ir.StatList(children=stats, symtab=self.symtab))

            condition_variable = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            loop_condition = ir.BinStat(dest=condition_variable, op='geq', srca=srca, srcb=srcb, symtab=self.symtab)

            diff = ir.BinStat(dest=srca, op='minus', srca=srca, srcb=srcb, symtab=self.symtab)
            loop_body = ir.StatList(children=[diff], symtab=self.symtab)

            while_loop = WhileStat(cond=loop_condition, body=loop_body, symtab=self.symtab)

            result_store = ir.StoreStat(dest=dest, symbol=srca, killhint=dest, symtab=self.symtab)

            stats += [while_loop, result_store]
            statl = ir.StatList(children=stats, symtab=self.symtab)

            # XXX: we need to lower it manually since it didn't exist before
            while_loop.lower()

            return self.parent.replace(self, statl)

        elif self.children[0] == "slash":
            """
            implement the division as a while loop
            so that `res = op1 / op2`
            becomes something like

            res = 0;
            while (op2 >= op1) {
                op2 = op2 - op1;
                res++;
            }
            """
            zero_destination = ir.LoadImmStat(dest=dest, val=0, symtab=self.symtab)

            one = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            load_one = ir.LoadImmStat(dest=one, val=1, symtab=self.symtab)

            condition_variable = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            loop_condition = ir.BinStat(dest=condition_variable, op="geq", srca=srca, srcb=srcb, symtab=self.symtab)

            op2_update = ir.BinStat(dest=srca, op="minus", srca=srca, srcb=srcb, symtab=self.symtab)
            calc_result = ir.BinStat(dest=dest, op="plus", srca=dest, srcb=one, symtab=self.symtab)
            loop_body = ir.StatList(children=[op2_update, calc_result], symtab=self.symtab)

            while_loop = WhileStat(cond=loop_condition, body=loop_body, symtab=self.symtab)

            stats += [zero_destination, load_one, while_loop]
            statl = ir.StatList(children=stats, symtab=self.symtab)

            # XXX: we need to lower it manually since it didn't exist before
            while_loop.lower()

            return self.parent.replace(self, statl)

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return BinExpr(parent=self.parent, children=new_children, symtab=self.symtab)


class UnExpr(Expr):
    def __init__(self, parent=None, children=None, symtab=None):
        log_indentation(bold(f"New UnExpr Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)

    def lower(self):
        src = self.children[1].destination()
        if self.children[0] in UNARY_CONDITIONALS:
            dest = ir.new_temporary(self.symtab, ir.TYPENAMES['boolean'])
        else:
            dest = ir.new_temporary(self.symtab, src.stype)
        stmt = ir.UnaryStat(dest=dest, op=self.children[0], src=src, symtab=self.symtab)
        statl = [self.children[1], stmt]
        return self.parent.replace(self, ir.StatList(children=statl, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return UnExpr(parent=self.parent, children=new_children, symtab=self.symtab)


# STATEMENTS

class Stat(ASTNode):  # abstract
    def __init__(self, parent=None, children=None, symtab=None):
        super().__init__(parent, children, symtab)
        self.label = None

    def set_label(self, label):
        self.label = label
        label.value = self  # set target

    def get_label(self):
        return self.label


class CallStat(Stat):
    """Procedure call"""

    def __init__(self, parent=None, function_symbol=None, parameters=[], returns=[], symtab=None):
        log_indentation(bold(f"New CallStat Node (id: {id(self)})"))
        super().__init__(parent, parameters, symtab)
        self.function_symbol = function_symbol
        self.returns = returns

    # raises RuntimeError if the number of parameters or of returns is wrong
    # TODO: add type checking
    def check_parameters_and_returns(self, function_definition):
        if len(function_definition.parameters) > len(self.children):
            raise RuntimeError(f"Passing too few parameters calling function {self.function_symbol.name}")
        if len(function_definition.parameters) < len(self.children):
            raise RuntimeError(f"Passing too many parameters calling function {self.function_symbol.name}")

        if len(function_definition.returns) > len(self.returns):
            raise RuntimeError(f"Too few values are being returned from function {function_definition.symbol.name}")
        elif len(function_definition.returns) < len(self.returns):
            raise RuntimeError(f"Too many values are being returned from function {function_definition.symbol.name}")

    def lower(self):
        # TODO: these need to be moved before the node expansion
        function_definition = FunctionTree.get_function_definition(self.function_symbol)
        function_definition.called_by_counter += 1

        self.check_parameters_and_returns(function_definition)

        parameters = [x.destination() for x in self.children]

        rets = []
        if len(self.returns) > 0:
            # XXX: self.returns_storage is created in the pre-lowering phase and it's
            #      a list with the temporaries that will contain the return values
            j = 0
            for i in range(len(self.returns)):
                if self.returns[i][0] == "_":
                    rets.append("_")
                else:
                    rets.append(self.returns_storage[j])
                    j += 1

        branch = ir.BranchStat(target=self.function_symbol, parameters=parameters, returns=rets, symtab=self.symtab)

        stats = self.children + [branch]

        return self.parent.replace(self, ir.StatList(children=stats, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_parameters = []
        for parameter in self.children:
            new_parameters.append(deepcopy(parameter, memo))

        new_function_symbol = deepcopy(self.function_symbol, memo)  # TODO: isn't this wrong?
        return CallStat(parent=self.parent, function_symbol=new_function_symbol, parameters=new_parameters, returns=self.returns, symtab=self.symtab)


class IfStat(Stat):
    def __init__(self, parent=None, cond=None, thenpart=None, elifspart=None, elsepart=None, symtab=None):
        log_indentation(bold(f"New IfStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.cond = cond
        self.thenpart = thenpart
        self.elifspart = elifspart
        self.elsepart = elsepart
        self.cond.parent = self
        self.thenpart.parent = self

        if self.elifspart:
            self.elifspart.parent = self

        if self.elsepart:
            self.elsepart.parent = self

    def lower(self):
        exit_label = ir.TYPENAMES['label']()
        exit_stat = ir.EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)

        # no elifs and no else
        if len(self.elifspart.children) == 0 and not self.elsepart:
            branch_to_exit = ir.BranchStat(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
            stat_list = ir.StatList(self.parent, [self.cond, branch_to_exit, self.thenpart, exit_stat], self.symtab)
            return self.parent.replace(self, stat_list)

        then_label = ir.TYPENAMES['label']()
        self.thenpart.set_label(then_label)
        branch_to_then = ir.BranchStat(cond=self.cond.destination(), target=then_label, symtab=self.symtab)
        branch_to_exit = ir.BranchStat(target=exit_label, symtab=self.symtab)
        no_exit_label = False  # decides whether or not to put the label at the end

        stats = [self.cond, branch_to_then]

        # elifs branches
        for i in range(0, len(self.elifspart.children), 2):
            elif_label = ir.TYPENAMES['label']()
            self.elifspart.children[i + 1].set_label(elif_label)
            branch_to_elif = ir.BranchStat(cond=self.elifspart.children[i].destination(), target=elif_label, symtab=self.symtab)
            stats += [self.elifspart.children[i], branch_to_elif]

        # NOTE: in general, avoid putting an exit label and a branch to it if the
        #       last instruction is a return

        # else
        if self.elsepart:
            last_else_instruction = self.elsepart.children[0].children[-1]
            if isinstance(last_else_instruction, ir.BranchStat) and last_else_instruction.is_return():
                stats += [self.elsepart]
                no_exit_label = True
            else:
                stats += [self.elsepart, branch_to_exit]
        else:  # there is no else, but there are elifs, jump to the end if no elif condition are met
            if len(self.elifspart.children) > 0:
                no_exit_label = False
                stats += [branch_to_exit]

        # elifs statements
        for i in range(0, len(self.elifspart.children), 2):
            elifspart = self.elifspart.children[i + 1]
            last_elif_instruction = elifspart.children[0].children[-1]

            if isinstance(last_elif_instruction, ir.BranchStat) and last_elif_instruction.is_return():
                stats += [elifspart]
                no_exit_label &= True
            else:
                stats += [elifspart, branch_to_exit]
                no_exit_label &= False  # if a single elif needs the exit label, put it there

        stats += [self.thenpart]
        last_then_instruction = self.thenpart.children[0].children[-1]
        if not (isinstance(last_then_instruction, ir.BranchStat) and last_then_instruction.is_return()) and not no_exit_label:
            stats += [branch_to_exit]

        if not no_exit_label:
            stats += [exit_stat]

        stat_list = ir.StatList(self.parent, stats, self.symtab)
        return self.parent.replace(self, stat_list)

    def __deepcopy__(self, memo):
        cond = deepcopy(self.cond, memo)
        thenpart = deepcopy(self.thenpart, memo)
        elifspart = deepcopy(self.elifspart, memo)
        elsepart = deepcopy(self.elsepart, memo)
        return IfStat(parent=self.parent, cond=cond, thenpart=thenpart, elifspart=elifspart, elsepart=elsepart, symtab=self.symtab)


class WhileStat(Stat):
    def __init__(self, parent=None, cond=None, body=None, symtab=None):
        log_indentation(bold(f"New WhileStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.cond = cond
        self.body = body
        self.cond.parent = self
        self.body.parent = self

    def lower(self):
        entry_label = ir.TYPENAMES['label']()
        exit_label = ir.TYPENAMES['label']()
        exit_stat = ir.EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)
        self.cond.set_label(entry_label)
        branch = ir.BranchStat(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
        loop = ir.BranchStat(target=entry_label, symtab=self.symtab)
        stat_list = ir.StatList(self.parent, [self.cond, branch, self.body, loop, exit_stat], self.symtab)
        return self.parent.replace(self, stat_list)

    def __deepcopy__(self, memo):
        new_cond = deepcopy(self.cond, memo)
        new_body = deepcopy(self.body, memo)
        return WhileStat(parent=self.parent, cond=new_cond, body=new_body, symtab=self.symtab)


class ForStat(Stat):
    def __init__(self, parent=None, init=None, cond=None, step=None, body=None, epilogue=None, symtab=None):
        log_indentation(bold(f"New ForStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.init = init
        self.cond = cond
        self.step = step
        self.body = body
        self.init.parent = self
        self.cond.parent = self
        self.step.parent = self
        self.body.parent = self

        self.epilogue = epilogue
        if self.epilogue is not None:
            self.epilogue.parent = self

    def lower(self):
        entry_label = ir.TYPENAMES['label']()
        exit_label = ir.TYPENAMES['label']()
        exit_stat = ir.EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)
        self.cond.set_label(entry_label)
        branch = ir.BranchStat(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
        loop = ir.BranchStat(target=entry_label, symtab=self.symtab)
        stat_list = ir.StatList(self.parent, [self.init, self.cond, branch, self.body, self.step, loop, exit_stat], self.symtab)

        if self.epilogue is not None:
            stat_list.append(self.epilogue)

        return self.parent.replace(self, stat_list)

    def __deepcopy__(self, memo):
        new_init = deepcopy(self.init, memo)
        new_cond = deepcopy(self.cond, memo)
        new_step = deepcopy(self.step, memo)
        new_body = deepcopy(self.body, memo)
        new_epilogue = deepcopy(self.epilogue, memo)
        return ForStat(parent=self.parent, init=new_init, cond=new_cond, step=new_step, body=new_body, epilogue=new_epilogue, symtab=self.symtab)


class AssignStat(Stat):
    def __init__(self, parent=None, children=[], target=None, offset=None, expr=None, symtab=None):
        log_indentation(bold(f"New AssignStat Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        self.symbol = target

        # TODO: why do this?
        try:
            self.symbol.parent = self
        except AttributeError:
            pass

        self.expr = expr
        if self.expr is not None:
            self.expr.parent = self

        self.offset = offset
        if self.offset is not None:
            self.offset.parent = self

    def lower(self):
        if self.children != []:  # if it has children, it means it has been expanded
            stats = self.children
            return self.parent.replace(self, ir.StatList(children=stats, symtab=self.symtab))

        dst = self.symbol

        # XXX: self.expr coud be a temporary
        try:
            src = self.expr.destination()
            stats = [self.expr]
        except AttributeError as e:
            if self.expr.is_temporary:
                src = self.expr
                stats = []
            else:
                raise e

        if not dst.is_string():
            if self.offset:  # TODO: this is the same as ArrayElement, but with a store instead of a load, merge the two
                stats += [self.offset]

                off = self.offset.destination()
                desttype = dst.stype
                if isinstance(desttype, ir.ArrayType):  # this is always true at the moment
                    desttype = desttype.basetype

                # TODO: avoid duplicating code here and in ArrayElement
                # at compile time, the dimensions of the array are always 0; we correct
                # this by getting the symbol that contains the real dynamic size of the
                # dimensions and substituiting the constant "0" with this symbol
                if self.symbol.alloct == 'heap':
                    dynamic_sizes = self.symbol.dynamic_sizes
                    i = 0
                    for child in self.offset.children:
                        if len(child.children) < 2:
                            continue

                        size_statement = child.children[1].children[0]
                        correct_size_statement = ir.LoadStat(dest=size_statement.dest, symbol=dynamic_sizes[i], symtab=size_statement.symtab)
                        child.children[1].replace(size_statement, correct_size_statement)

                        i += 1

                if self.symbol.alloct == 'param' or self.symbol.is_string():
                    # pass by reference, we have to deallocate the pointer twice
                    parameter = ir.new_temporary(self.symtab, ir.PointerType(ir.PointerType(self.symbol.stype.basetype)))
                    loadparameter = ir.LoadPtrToSym(dest=parameter, symbol=self.symbol, symtab=self.symtab)

                    array_pointer = ir.new_temporary(self.symtab, ir.PointerType(desttype))
                    loadptr = ir.LoadStat(dest=array_pointer, symbol=parameter, symtab=self.symtab)
                    stats += [loadparameter, loadptr]
                else:
                    array_pointer = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.stype.basetype))
                    loadptr = ir.LoadPtrToSym(dest=array_pointer, symbol=self.symbol, symtab=self.symtab)

                    stats += [loadptr]

                dst = ir.new_temporary(self.symtab, ir.PointerType(desttype))
                add = ir.BinStat(dest=dst, op='plus', srca=array_pointer, srcb=off, symtab=self.symtab)
                stats += [add]

            if dst.is_temporary and dst.is_scalar():
                stats += [ir.StoreStat(dest=dst, symbol=src, killhint=dst, symtab=self.symtab)]
            else:
                stats += [ir.StoreStat(dest=dst, symbol=src, symtab=self.symtab)]

            return self.parent.replace(self, ir.StatList(children=stats, symtab=self.symtab))

        """
        Assign a variable to a fixed string by getting a fixed string from the data section, then
        copying one by one its characters from the fixed string to the variable one
        """
        ptrreg_data = src

        # load the variable data string address
        ptrreg_var = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.stype.basetype))
        access_var = ir.LoadPtrToSym(dest=ptrreg_var, symbol=self.symbol, symtab=self.symtab)

        if self.offset:
            stats += [access_var, self.offset]
            access_var = ir.BinStat(dest=ptrreg_var, op='plus', srca=ptrreg_var, srcb=self.offset.destination(), symtab=self.symtab)

        counter = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        counter_initialize = ir.LoadImmStat(dest=counter, val=0, symtab=self.symtab)

        zero = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        zero_initialize = ir.LoadImmStat(dest=zero, val=0, symtab=self.symtab)

        one = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        one_initialize = ir.LoadImmStat(dest=one, val=1, symtab=self.symtab)

        # load first char of data
        character = ir.new_temporary(self.symtab, ir.TYPENAMES['char'])
        load_data_char = ir.LoadStat(dest=character, symbol=ptrreg_data, symtab=self.symtab)

        # while the char loaded from the fixed string is different from 0x0,
        # copy the chars from the fixed string to the variable one
        dest = ir.new_temporary(self.symtab, ir.TYPENAMES['boolean'])
        cond = ir.BinStat(dest=dest, op='neq', srca=character, srcb=zero, symtab=self.symtab)

        store_var_char = ir.StoreStat(dest=ptrreg_var, symbol=character, symtab=self.symtab)

        increment_data = ir.BinStat(dest=ptrreg_data, op='plus', srca=ptrreg_data, srcb=one, symtab=self.symtab)
        increment_var = ir.BinStat(dest=ptrreg_var, op='plus', srca=ptrreg_var, srcb=one, symtab=self.symtab)
        increment_counter = ir.BinStat(dest=counter, op='plus', srca=counter, srcb=one, symtab=self.symtab)

        body_stats = [store_var_char, increment_data, increment_var, increment_counter, load_data_char]

        body = ir.StatList(children=body_stats, symtab=self.symtab)
        while_loop = WhileStat(cond=cond, body=body, symtab=self.symtab)

        # put a terminator 0x0 byte in the variable string
        end_zero_string = ir.StoreStat(dest=ptrreg_var, symbol=zero, symtab=self.symtab)

        stats += [access_var, counter_initialize, zero_initialize, one_initialize, load_data_char, while_loop, end_zero_string]
        statl = ir.StatList(children=stats, symtab=self.symtab)

        # XXX: we need to lower it manually since it didn't exist before
        while_loop.lower()

        return self.parent.replace(self, statl)

    def __deepcopy__(self, memo):
        new_expr = deepcopy(self.expr, memo)
        new_offset = deepcopy(self.offset, memo)

        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return AssignStat(parent=self.parent, children=new_children, target=self.symbol, offset=new_offset, expr=new_expr, symtab=self.symtab)


class PrintStat(Stat):
    def __init__(self, parent=None, children=[], expr=None, newline=True, symtab=None):
        log_indentation(bold(f"New PrintStat Node (id: {id(self)})"))
        if children != []:
            super().__init__(parent, children, symtab)
        else:
            super().__init__(parent, [expr], symtab)
        self.newline = newline

    def lower(self):
        if len(self.children) > 1:
            stats = self.children
            return self.parent.replace(self, ir.StatList(children=stats, symtab=self.symtab))

        print_type = ir.TYPENAMES['int']

        if self.children[0] and self.children[0].destination().is_string():
            print_type = ir.TYPENAMES['char']
        elif self.children[0] and self.children[0].destination().is_boolean():
            print_type = ir.TYPENAMES['boolean']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 16 and 'unsigned' in self.children[0].destination().stype.qualifiers:
            print_type = ir.TYPENAMES['ushort']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 8 and 'unsigned' in self.children[0].destination().stype.qualifiers:
            print_type = ir.TYPENAMES['ubyte']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 16:
            print_type = ir.TYPENAMES['short']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 8:
            print_type = ir.TYPENAMES['byte']

        pc = ir.PrintStat(src=self.children[0].destination(), print_type=print_type, newline=self.newline, symtab=self.symtab)
        stlist = ir.StatList(children=[self.children[0], pc], symtab=self.symtab)
        return self.parent.replace(self, stlist)

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return PrintStat(parent=self.parent, children=new_children, expr=new_children[0], newline=self.newline, symtab=self.symtab)


class ReadStat(Stat):
    def __init__(self, parent=None, symtab=None):
        log_indentation(bold(f"New ReadStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)

    def lower(self):
        tmp = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        read = ir.ReadStat(dest=tmp, symtab=self.symtab)
        stlist = ir.StatList(children=[read], symtab=self.symtab)
        return self.parent.replace(self, stlist)

    def __deepcopy__(self, memo):
        return ReadStat(parent=self.parent, symtab=self.symtab)


class ReturnStat(Stat):
    def __init__(self, parent=None, children=[], symtab=None):
        log_indentation(bold(f"New ReturnStat Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)

    def type_checking(self, returns, function_returns):
        masks = []

        for i in range(len(returns)):
            if returns[i].stype.name == function_returns[i].stype.name:
                continue

            if returns[i].stype.is_numeric() and function_returns[i].stype.is_numeric():
                if returns[i].stype.size > function_returns[i].stype.size:
                    continue  # we can return, for example, a byte as an int

                masks += mask_numeric(returns[i], self.symtab)
                continue

            # check if we're returning a pointer when we were expecting an array, it's good since we only return references
            # TODO: check that we are not returning local references
            if returns[i].is_pointer() and function_returns[i].is_array() and (returns[i].stype.pointstotype.name == function_returns[i].stype.basetype.name):
                continue

            raise RuntimeError(f"Trying to return a value of type {returns[i].stype.name} instead of {function_returns[i].stype.name}")

        return masks

    def lower(self):
        stats = self.children

        function_definition = self.get_function()
        if function_definition.parent is None:
            raise RuntimeError("The main function should not have return statements")

        # check that the function returns as many values as the defined ones
        if len(function_definition.returns) > len(self.children):
            raise RuntimeError(f"Too few values are being returned in function {function_definition.symbol.name}")
        elif len(function_definition.returns) < len(self.children):
            raise RuntimeError(f"Too many values are being returned in function {function_definition.symbol.name}")

        returns = [x.destination() for x in self.children]
        stats += self.type_checking(returns, function_definition.returns)

        stats.append(ir.BranchStat(parent=self, target=None, parameters=function_definition.parameters, returns=returns, symtab=self.symtab))

        stat_list = ir.StatList(self.parent, stats, self.symtab)
        return self.parent.replace(self, stat_list)

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return ReturnStat(parent=self.parent, children=new_children, symtab=self.symtab)


class NewStat(Stat):
    def __init__(self, parent=None, children=[], expr=None, symtab=None):
        log_indentation(bold(f"New NewStat Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        self.expr = expr
        if self.expr is not None:
            self.expr.parent = self

    def lower(self):
        target = self.children[0]

        # how much space in the heap to save
        size = target.stype.size // 8

        # this temporary will be used each time the target symbol is used
        memory_addr = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        target.set_address(memory_addr)

        # get the current value of the BRK and put it in the memory_addr temporary
        data_symtab = ir.DataSymbolTable.get_data_symtab()
        brk_symbol = data_symtab.find(self, "brk")
        brk_temp = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])

        get_brk = ir.LoadStat(dest=memory_addr, symbol=brk_symbol, symtab=self.symtab)

        # TODO: check that BRK is not BRK_MAX

        # add to the BRK, reserrving the space for the target
        size_temp = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        if self.expr is None:
            load_size = ir.LoadImmStat(dest=size_temp, val=size, symtab=self.symtab)
        else:  # this is an array so the size is computed using a list of expressions
            statl = []

            # the size is the result of the expressions (defined as [expr1][expr2]) times the basetype size
            load_type_size = ir.LoadImmStat(dest=size_temp, val=target.stype.basetype.size // 8, symtab=self.symtab)
            statl.append(load_type_size)

            for expr in self.expr.children:
                statl.append(expr)

                multiply_size = ir.BinStat(dest=size_temp, op='times', srca=size_temp, srcb=expr.destination(), symtab=self.symtab)
                statl.append(multiply_size)

            load_size = ir.StatList(self, statl, symtab=self.symtab)

            # give the target the array with all the symbols containing its sizes
            target.set_dynamic_sizes([expr.destination() for expr in self.expr.children])

        reduce_brk = ir.BinStat(dest=brk_temp, op='plus', srca=memory_addr, srcb=size_temp, symtab=self.symtab)

        store_brk = ir.StoreStat(dest=brk_symbol, symbol=brk_temp, symtab=self.symtab)

        stat_list = ir.StatList(self.parent, [get_brk, load_size, reduce_brk, store_brk], self.symtab)
        return self.parent.replace(self, stat_list)
