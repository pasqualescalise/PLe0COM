#!/usr/bin/env python3

"""Abstract Syntax Tree

Representation of the source code as a tree, created by the parser. Nodes
represent variables, expressions or statements.
Each node has to implement the following methods:
    + lower, to convert itself into a List of IR instructions; all
      of these InstructionLists are successively flattened
    + __deepcopy__, specifying a method to copy them and their attributes
"""

from copy import deepcopy
from math import log

from ir.function_tree import FunctionTree
import ir.ir as ir
from logger import log_indentation, ii, cyan, bold
import logger


# UTILITIES

UNARY_CONDITIONALS = ['odd']
BINARY_CONDITIONALS = ['eql', 'neq', 'lss', 'leq', 'gtr', 'geq']


# Returns instructions that mask shorts and bytes, to eliminate sign extension
def mask_numeric(operand, symtab):
    mask = [int(0x000000ff), int(0x0000ffff)][operand.type.size // 8 - 1]  # either byte or short
    mask_temp = ir.new_temporary(symtab, ir.TYPENAMES['int'])
    load_mask = ir.LoadImmInstruction(dest=mask_temp, val=mask, symtab=symtab)
    apply_mask = ir.BinaryInstruction(dest=operand, op="and", srca=operand, srcb=load_mask.destination(), symtab=symtab)
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
        self.type = None

    # XXX: must only be used for printing
    def type_repr(self):
        return ".".join(str(type(self)).split("'")[1].split(".")[-2:])

    def __repr__(self):
        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'local_symtab', 'offset', 'function_symbol', 'parameters', 'returns', 'called_by_counter', 'epilogue', 'values', 'type'} & set(dir(self))

        res = f"{cyan(f'{self.type_repr()}')}, {id(self)}" + " {"
        if self.parent is not None:
            # res += f"\nparent: {id(self.parent)};\n"
            res += "\n"

        res = f"{res}"

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
                log_indentation(f"Navigating to {cyan(len(self.children))} children of {cyan(self.type_repr())}, {id(self)}")
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
                    log_indentation(f"Navigating to attribute {cyan(attr)} of {cyan(self.type_repr())}, {id(self)}")
                logger.indentation += 1
                node = getattr(self, attr)
                node.navigate(action, *args, quiet=quiet)
                logger.indentation -= 1
            except AttributeError:
                logger.indentation -= 1
        if not quiet:
            log_indentation(f"Navigating to {cyan(self.type_repr())}, {id(self)}")

        # XXX: shitty solution
        try:
            action(self, *args, quiet=quiet)
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
    def __init__(self, parent=None, value=0, symbol=None, type=None, symtab=None):
        log_indentation(bold(f"New Const Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value
        self.symbol = symbol
        self.type = type

    def lower(self):  # TODO: make it possible to define constant booleans
        if self.value in ["True", "False"]:
            new = ir.new_temporary(self.symtab, ir.TYPENAMES['boolean'])
            loadst = ir.LoadImmInstruction(dest=new, val=self.value, symtab=self.symtab)
        elif self.symbol is None:
            new = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            loadst = ir.LoadImmInstruction(dest=new, val=self.value, symtab=self.symtab)
        else:
            new = ir.new_temporary(self.symtab, self.symbol.type)
            loadst = ir.LoadInstruction(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, ir.InstructionList(children=[loadst], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return Const(parent=self.parent, value=self.value, symbol=self.symbol, type=self.type, symtab=self.symtab)


class Var(ASTNode):
    """loads in a temporary the value pointed to by the symbol"""

    def __init__(self, parent=None, symbol=None, offset=None, type=None, symtab=None):
        log_indentation(bold(f"New Var Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.symbol = symbol
        self.offset = offset
        if self.offset is not None:
            self.offset.parent = self
        self.type = type

    def lower(self):
        if self.offset is None:
            return self.lower_scalar()
        return self.lower_array()

    def lower_scalar(self):
        if self.symbol.is_string() and self.symbol.alloct != 'param':  # load strings as char pointers
            ptrreg = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.type.basetype))
            loadptr = ir.LoadPointerInstruction(dest=ptrreg, symbol=self.symbol, symtab=self.symtab)
            return self.parent.replace(self, ir.InstructionList(children=[loadptr], symtab=self.symtab))

        elif self.symbol.is_array() and self.symbol.alloct != 'param':  # load arrays as pointers
            ptrreg = ir.new_temporary(self.symtab, ir.PointerType(ir.PointerType(self.symbol.type.basetype)))
            loadptr = ir.LoadPointerInstruction(dest=ptrreg, symbol=self.symbol, symtab=self.symtab)
            return self.parent.replace(self, ir.InstructionList(children=[loadptr], symtab=self.symtab))

        new = ir.new_temporary(self.symtab, self.symbol.type)
        loadst = ir.LoadInstruction(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, ir.InstructionList(children=[loadst], symtab=self.symtab))

    def lower_array(self):
        array_pointer = self.offset.destination()
        instrs = [self.offset]

        if not self.type.is_string():  # do not go deeper inside strings
            dest = ir.new_temporary(self.symtab, self.symbol.type.basetype)
            load_array_pointer = ir.LoadInstruction(dest=dest, symbol=array_pointer, symtab=self.symtab)
            instrs += [load_array_pointer]

        return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

    def __deepcopy__(self, memo):
        offset = deepcopy(self.offset)
        return Var(parent=self.parent, symbol=self.symbol, offset=offset, type=self.type, symtab=self.symtab)


class ArrayElement(ASTNode):
    def __init__(self, parent=None, symbol=None, indexes=[], type=None, symtab=None):
        log_indentation(bold(f"New ArrayElement Node (id: {id(self)})"))
        super().__init__(parent, indexes, symtab)
        self.symbol = symbol
        self.type = type

    def lower_offset(self):  # TODO: add code to check at runtime if we went over the array size
        instrs = self.children[:]

        stride = self.type.size // 8
        type_indices = self.symbol.type.dims

        accumulator = None
        index_magnitude = 1  # how far in the array are we, multiplied by the array dimensions
        for i in range(len(self.children) - 1, -1, -1):  # backwards
            multiplier = stride * index_magnitude
            multiplier_temp = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            multiplier_initialize = ir.LoadImmInstruction(dest=multiplier_temp, val=multiplier, symtab=self.symtab)
            instrs += [multiplier_initialize]

            index_temp = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            calc_index = ir.BinaryInstruction(dest=index_temp, op='times', srca=self.children[i].destination(), srcb=multiplier_temp, symtab=self.symtab)
            instrs += [calc_index]

            if i == len(self.children) - 1:
                accumulator = index_temp
            else:
                add_temps = ir.BinaryInstruction(dest=index_temp, op='plus', srca=accumulator, srcb=index_temp, symtab=self.symtab)
                instrs += [add_temps]
                accumulator = index_temp  # XXX: change accumulator each time to reduce register pressure

            index_magnitude *= type_indices[i]

        return instrs

    def lower(self):
        src = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.type.basetype))
        instrs = self.lower_offset()
        off = instrs[-1].destination()

        if self.symbol.alloct == 'param':
            # pass by reference, we have to deallocate the pointer twice
            parameter = ir.new_temporary(self.symtab, ir.PointerType(ir.PointerType(self.symbol.type.basetype)))
            loadparameter = ir.LoadPointerInstruction(dest=parameter, symbol=self.symbol, symtab=self.symtab)

            array_pointer = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.type.basetype))
            loadptr = ir.LoadInstruction(dest=array_pointer, symbol=parameter, symtab=self.symtab)
            instrs += [loadparameter, loadptr]
        else:
            array_pointer = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.type.basetype))
            loadptr = ir.LoadPointerInstruction(dest=array_pointer, symbol=self.symbol, symtab=self.symtab)

            instrs += [loadptr]

        add = ir.BinaryInstruction(dest=src, op='plus', srca=array_pointer, srcb=off, symtab=self.symtab)
        instrs += [add]

        return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return ArrayElement(parent=self.parent, symbol=self.symbol, indexes=new_children, type=self.type, symtab=self.symtab)


class String(ASTNode):
    """Puts a fixed string in the data SymbolTable"""

    def __init__(self, parent=None, value="", type=None, symtab=None):
        log_indentation(bold(f"New String Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value
        self.type = type

    def lower(self):
        # put the string in the data SymbolTable
        data_variable = ir.DataSymbolTable.add_data_symbol(self.type, value=self.value)

        # load the fixed data string address
        ptrreg_data = ir.new_temporary(self.symtab, ir.PointerType(data_variable.type.basetype))
        access_string = ir.LoadPointerInstruction(dest=ptrreg_data, symbol=data_variable, symtab=self.symtab)

        return self.parent.replace(self, ir.InstructionList(children=[access_string], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return String(parent=self.parent, value=self.value, type=self.type, symtab=self.symtab)


class StaticArray(ASTNode):
    # XXX: this doesn't get lowered, other nodes expand themselves and
    #      access the array values one by one

    def __init__(self, parent=None, values=[], values_type=None, symtab=None):
        log_indentation(bold(f"New StaticArray Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.values = values
        self.values_type = values_type
        for value in self.values:
            value.parent = self

        self.type_checking()  # call this manually since this node will not survive until regular type checking

    def __deepcopy__(self, memo):
        new_values = []
        for value in self.values:
            new_values.append(deepcopy(value, memo))

        return StaticArray(parent=self.parent, values=new_values, values_type=self.values_type, symtab=self.symtab)


# EXPRESSIONS

class Expr(ASTNode):  # abstract
    def get_operator(self):
        return self.children[0]


class BinaryExpr(Expr):
    def __init__(self, parent=None, children=None, type=None, symtab=None):
        log_indentation(bold(f"New BinaryExpr Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        self.type = type

    def lower(self):
        instrs = [self.children[1], self.children[2]]

        srca = self.children[1].destination()
        srcb = self.children[2].destination()

        if self.mask:  # set during type checking
            smallest_operand = srca if srca.type.size < srcb.type.size else srcb
            instrs += mask_numeric(smallest_operand, self.symtab)

        dest = ir.new_temporary(self.symtab, self.type)

        if self.children[0] not in ["slash", "mod"]:
            expression = ir.BinaryInstruction(dest=dest, op=self.children[0], srca=srca, srcb=srcb, symtab=self.symtab)
            instrs += [expression]
            return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

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
            if isinstance(self.children[2].children[0], ir.LoadImmInstruction) and log(self.children[2].children[0].val, 2).is_integer():
                expression = ir.BinaryInstruction(dest=dest, op="mod", srca=srca, srcb=srcb, symtab=self.symtab)
                instrs += [expression]
                return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

            condition_variable = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            loop_condition = ir.BinaryInstruction(dest=condition_variable, op='geq', srca=srca, srcb=srcb, symtab=self.symtab)

            diff = ir.BinaryInstruction(dest=srca, op='minus', srca=srca, srcb=srcb, symtab=self.symtab)
            loop_body = ir.InstructionList(children=[diff], symtab=self.symtab)

            while_loop = WhileStat(cond=loop_condition, body=loop_body, symtab=self.symtab)

            # XXX: we need to lower it manually since it didn't exist before
            while_statements = StatList(children=[while_loop], symtab=self.symtab)
            while_loop.lower()
            instrs += while_statements.children

            result_store = ir.StoreInstruction(dest=dest, symbol=srca, symtab=self.symtab)
            instrs += [result_store]

            return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

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
            zero_destination = ir.LoadImmInstruction(dest=dest, val=0, symtab=self.symtab)

            one = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            load_one = ir.LoadImmInstruction(dest=one, val=1, symtab=self.symtab)
            instrs += [zero_destination, load_one]

            condition_variable = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
            loop_condition = ir.BinaryInstruction(dest=condition_variable, op="geq", srca=srca, srcb=srcb, symtab=self.symtab)

            op2_update = ir.BinaryInstruction(dest=srca, op="minus", srca=srca, srcb=srcb, symtab=self.symtab)
            calc_result = ir.BinaryInstruction(dest=dest, op="plus", srca=dest, srcb=one, symtab=self.symtab)
            loop_body = ir.InstructionList(children=[op2_update, calc_result], symtab=self.symtab)

            while_loop = WhileStat(cond=loop_condition, body=loop_body, symtab=self.symtab)

            # XXX: we need to lower it manually since it didn't exist before
            while_statements = StatList(children=[while_loop], symtab=self.symtab)
            while_loop.lower()
            instrs += while_statements.children

            return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return BinaryExpr(parent=self.parent, children=new_children, type=self.type, symtab=self.symtab)


class UnaryExpr(Expr):
    def __init__(self, parent=None, children=None, type=None, symtab=None):
        log_indentation(bold(f"New UnaryExpr Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        self.type = type

    def lower(self):
        src = self.children[1].destination()
        dest = ir.new_temporary(self.symtab, self.type)
        expression = ir.UnaryInstruction(dest=dest, op=self.children[0], src=src, symtab=self.symtab)
        instrs = [self.children[1], expression]
        return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return UnaryExpr(parent=self.parent, children=new_children, type=self.type, symtab=self.symtab)


# STATEMENTS

class Stat(ASTNode):  # abstract
    def __init__(self, parent=None, children=None, symtab=None):
        super().__init__(parent, children, symtab)


class CallStat(Stat):
    """Procedure call"""

    def __init__(self, parent=None, function_symbol=None, parameters=[], returns=[], type=None, symtab=None):
        log_indentation(bold(f"New CallStat Node (id: {id(self)})"))
        super().__init__(parent, parameters, symtab)
        self.function_symbol = function_symbol
        self.returns = returns
        self.type = type

    def lower(self):
        function_definition = FunctionTree.get_function_definition(self.function_symbol)
        function_definition.called_by_counter += 1

        parameters = [x.destination() for x in self.children]

        rets = []
        if len(self.returns) > 0:
            # XXX: self.returns_storage is created in the pre-lowering phase and it's
            #      a list with the temporaries that will contain the return values
            j = 0
            for i in range(len(self.returns)):
                if self.returns[i] == "_":
                    rets.append("_")
                else:
                    rets.append(self.returns_storage[j])
                    j += 1

        branch = ir.BranchInstruction(target=self.function_symbol, parameters=parameters, returns=rets, symtab=self.symtab)

        instrs = self.children + [branch]

        return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_parameters = []
        for parameter in self.children:
            new_parameters.append(deepcopy(parameter, memo))

        new_function_symbol = deepcopy(self.function_symbol, memo)  # TODO: isn't this wrong?
        return CallStat(parent=self.parent, function_symbol=new_function_symbol, parameters=new_parameters, returns=self.returns, type=self.type, symtab=self.symtab)


class IfStat(Stat):
    def __init__(self, parent=None, cond=None, thenpart=None, elifspart=None, elifs_conditions=[], elsepart=None, type=None, symtab=None):
        log_indentation(bold(f"New IfStat Node (id: {id(self)})"))
        super().__init__(parent, elifs_conditions, symtab)
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

        self.type = type

    def lower(self):
        exit_label = ir.TYPENAMES['label']()
        exit_instr = ir.LabelInstruction(self.parent, label=exit_label, symtab=self.symtab)

        # no elifs and no else
        if len(self.elifspart.children) == 0 and not self.elsepart:
            branch_to_exit = ir.BranchInstruction(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
            return self.parent.replace(self, ir.InstructionList(self.parent, [self.cond, branch_to_exit, self.thenpart, exit_instr], self.symtab))

        then_label = ir.TYPENAMES['label']()
        then_label_instr = ir.LabelInstruction(self.parent, label=then_label, symtab=self.symtab)
        branch_to_then = ir.BranchInstruction(cond=self.cond.destination(), target=then_label, symtab=self.symtab)
        branch_to_exit = ir.BranchInstruction(target=exit_label, symtab=self.symtab)
        no_exit_label = False  # decides whether or not to put the label at the end

        instrs = [self.cond, branch_to_then]

        # elifs branches
        elifs_label_insts = []
        for i in range(0, len(self.elifspart.children)):
            elif_label = ir.TYPENAMES['label']()
            elifs_label_insts.append(ir.LabelInstruction(self.parent, label=elif_label, symtab=self.symtab))
            branch_to_elif = ir.BranchInstruction(cond=self.children[i].destination(), target=elif_label, symtab=self.symtab)
            instrs += [self.children[i], branch_to_elif]

        # NOTE: in general, avoid putting an exit label and a branch to it if the
        #       last instruction is a return

        # else
        if self.elsepart:
            last_else_instruction = self.elsepart.children[0].children[-1]
            if isinstance(last_else_instruction, ir.BranchInstruction) and last_else_instruction.is_return():
                instrs += [self.elsepart]
                no_exit_label = True
            else:
                instrs += [self.elsepart, branch_to_exit]
        else:  # there is no else, but there are elifs, jump to the end if no elif condition are met
            if len(self.elifspart.children) > 0:
                no_exit_label = False
                instrs += [branch_to_exit]

        # elifs statements
        for i in range(0, len(self.elifspart.children)):
            elifspart = self.elifspart.children[i]
            last_elif_instruction = elifspart.children[0].children[-1]

            if isinstance(last_elif_instruction, ir.BranchInstruction) and last_elif_instruction.is_return():
                instrs += [elifs_label_insts[i], elifspart]
                no_exit_label &= True
            else:
                instrs += [elifs_label_insts[i], elifspart, branch_to_exit]
                no_exit_label &= False  # if a single elif needs the exit label, put it there

        instrs += [then_label_instr, self.thenpart]
        last_then_instruction = self.thenpart.children[0].children[-1]
        if not (isinstance(last_then_instruction, ir.BranchInstruction) and last_then_instruction.is_return()) and not no_exit_label:
            instrs += [branch_to_exit]

        if not no_exit_label:
            instrs += [exit_instr]

        return self.parent.replace(self, ir.InstructionList(self.parent, instrs, self.symtab))

    def __deepcopy__(self, memo):
        cond = deepcopy(self.cond, memo)
        thenpart = deepcopy(self.thenpart, memo)
        elifspart = deepcopy(self.elifspart, memo)
        elsepart = deepcopy(self.elsepart, memo)
        return IfStat(parent=self.parent, cond=cond, thenpart=thenpart, elifspart=elifspart, elsepart=elsepart, type=self.type, symtab=self.symtab)


class WhileStat(Stat):
    def __init__(self, parent=None, cond=None, body=None, type=None, symtab=None):
        log_indentation(bold(f"New WhileStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.cond = cond
        self.body = body
        self.cond.parent = self
        self.body.parent = self
        self.type = type

    def lower(self):
        entry_label = ir.TYPENAMES['label']()
        entry_instr = ir.LabelInstruction(self.parent, label=entry_label, symtab=self.symtab)
        exit_label = ir.TYPENAMES['label']()
        exit_instr = ir.LabelInstruction(self.parent, label=exit_label, symtab=self.symtab)
        branch = ir.BranchInstruction(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
        loop = ir.BranchInstruction(target=entry_label, symtab=self.symtab)
        return self.parent.replace(self, ir.InstructionList(self.parent, [entry_instr, self.cond, branch, self.body, loop, exit_instr], self.symtab))

    def __deepcopy__(self, memo):
        new_cond = deepcopy(self.cond, memo)
        new_body = deepcopy(self.body, memo)
        return WhileStat(parent=self.parent, cond=new_cond, body=new_body, type=self.type, symtab=self.symtab)


class ForStat(Stat):
    def __init__(self, parent=None, init=None, cond=None, step=None, body=None, epilogue=None, type=None, symtab=None):
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
            self.type = type

    def lower(self):
        entry_label = ir.TYPENAMES['label']()
        entry_instr = ir.LabelInstruction(self.parent, label=entry_label, symtab=self.symtab)
        exit_label = ir.TYPENAMES['label']()
        exit_instr = ir.LabelInstruction(self.parent, label=exit_label, symtab=self.symtab)
        branch = ir.BranchInstruction(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
        loop = ir.BranchInstruction(target=entry_label, symtab=self.symtab)

        instrs = [self.init, entry_instr, self.cond, branch, self.body, self.step, loop, exit_instr]

        if self.epilogue is not None:
            instrs += [self.epilogue]

        return self.parent.replace(self, ir.InstructionList(self.parent, instrs, self.symtab))

    def __deepcopy__(self, memo):
        new_init = deepcopy(self.init, memo)
        new_cond = deepcopy(self.cond, memo)
        new_step = deepcopy(self.step, memo)
        new_body = deepcopy(self.body, memo)
        new_epilogue = deepcopy(self.epilogue, memo)
        return ForStat(parent=self.parent, init=new_init, cond=new_cond, step=new_step, body=new_body, epilogue=new_epilogue, type=self.type, symtab=self.symtab)


class AssignStat(Stat):
    def __init__(self, parent=None, children=[], symbol=None, offset=None, expr=None, type=None, symtab=None):
        log_indentation(bold(f"New AssignStat Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        self.symbol = symbol

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

        self.type = type

    def lower(self):
        dest = self.symbol

        # XXX: self.expr coud be a temporary
        try:
            src = self.expr.destination()
            instrs = [self.expr]
        except AttributeError as e:
            if self.expr.is_temporary:
                src = self.expr
                instrs = []
            else:
                raise e

        if not dest.is_string() and not (self.offset is not None and src.is_string()):
            if self.offset:
                dest = self.offset.destination()
                instrs += [self.offset]

            instrs += [ir.StoreInstruction(dest=dest, symbol=src, symtab=self.symtab)]

            return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

        """
        Assign a variable to a fixed string by getting a fixed string from the data section, then
        copying one by one its characters from the fixed string to the variable one
        """
        ptrreg_data = src

        # load the variable data string address
        if self.offset:
            instrs += [self.offset]
            ptrreg_var = self.offset.destination()  # string array
        else:
            ptrreg_var = ir.new_temporary(self.symtab, ir.PointerType(self.symbol.type.basetype))
            access_var = ir.LoadPointerInstruction(dest=ptrreg_var, symbol=self.symbol, symtab=self.symtab)
            instrs += [access_var]

        counter = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        counter_initialize = ir.LoadImmInstruction(dest=counter, val=0, symtab=self.symtab)

        zero = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        zero_initialize = ir.LoadImmInstruction(dest=zero, val=0, symtab=self.symtab)

        one = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        one_initialize = ir.LoadImmInstruction(dest=one, val=1, symtab=self.symtab)

        # load first char of data
        character = ir.new_temporary(self.symtab, ir.TYPENAMES['char'])
        load_data_char = ir.LoadInstruction(dest=character, symbol=ptrreg_data, symtab=self.symtab)

        instrs += [counter_initialize, zero_initialize, one_initialize, load_data_char]

        # while the char loaded from the fixed string is different from 0x0,
        # copy the chars from the fixed string to the variable one
        dest = ir.new_temporary(self.symtab, ir.TYPENAMES['boolean'])
        cond = ir.BinaryInstruction(dest=dest, op='neq', srca=character, srcb=zero, symtab=self.symtab)

        store_var_char = ir.StoreInstruction(dest=ptrreg_var, symbol=character, symtab=self.symtab)

        increment_data = ir.BinaryInstruction(dest=ptrreg_data, op='plus', srca=ptrreg_data, srcb=one, symtab=self.symtab)
        increment_var = ir.BinaryInstruction(dest=ptrreg_var, op='plus', srca=ptrreg_var, srcb=one, symtab=self.symtab)
        increment_counter = ir.BinaryInstruction(dest=counter, op='plus', srca=counter, srcb=one, symtab=self.symtab)

        loop_body = ir.InstructionList(children=[store_var_char, increment_data, increment_var, increment_counter, load_data_char], symtab=self.symtab)
        while_loop = WhileStat(cond=cond, body=loop_body, symtab=self.symtab)

        # XXX: we need to lower it manually since it didn't exist before
        while_statements = StatList(children=[while_loop], symtab=self.symtab)
        while_loop.lower()
        instrs += while_statements.children

        # put a terminator 0x0 byte in the variable string
        end_zero_string = ir.StoreInstruction(dest=ptrreg_var, symbol=zero, symtab=self.symtab)
        instrs += [end_zero_string]

        return self.parent.replace(self, ir.InstructionList(children=instrs, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_expr = deepcopy(self.expr, memo)
        new_offset = deepcopy(self.offset, memo)
        return AssignStat(parent=self.parent, symbol=self.symbol, offset=new_offset, expr=new_expr, type=self.type, symtab=self.symtab)


class PrintStat(Stat):
    def __init__(self, parent=None, children=[], expr=None, newline=True, type=None, symtab=None):
        log_indentation(bold(f"New PrintStat Node (id: {id(self)})"))
        if children != []:
            super().__init__(parent, children, symtab)
        else:
            super().__init__(parent, [expr], symtab)
        self.newline = newline
        self.type = type

    def lower(self):
        print_type = self.print_type  # set during type checking

        pc = ir.PrintInstruction(src=self.children[0].destination(), print_type=print_type, newline=self.newline, symtab=self.symtab)
        return self.parent.replace(self, ir.InstructionList(children=[self.children[0], pc], symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return PrintStat(parent=self.parent, children=new_children, expr=new_children[0], newline=self.newline, type=self.type, symtab=self.symtab)


class ReadStat(Stat):
    def __init__(self, parent=None, type=None, symtab=None):
        log_indentation(bold(f"New ReadStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.type = type

    def lower(self):
        tmp = ir.new_temporary(self.symtab, ir.TYPENAMES['int'])
        read = ir.ReadInstruction(dest=tmp, symtab=self.symtab)
        return self.parent.replace(self, ir.InstructionList(children=[read], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return ReadStat(parent=self.parent, type=self.type, symtab=self.symtab)


class ReturnStat(Stat):
    def __init__(self, parent=None, children=[], type=None, symtab=None):
        log_indentation(bold(f"New ReturnStat Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        for child in self.children:
            child.parent = self
        self.type = type

    def apply_masks(self, returns):
        masks = []
        for index in self.masks:  # set during type checking
            masks += mask_numeric(returns[index], self.symtab)

        return masks

    def lower(self):
        instrs = self.children[:]

        function_definition = self.get_function()
        if function_definition.parent is None:
            raise RuntimeError("The main function should not have return statements")

        returns = [x.destination() for x in self.children]
        instrs += self.apply_masks(returns)

        return_branch = ir.BranchInstruction(parent=self, target=None, parameters=function_definition.parameters, returns=returns, symtab=self.symtab)
        instrs += [return_branch]

        return self.parent.replace(self, ir.InstructionList(self.parent, instrs, self.symtab))

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return ReturnStat(parent=self.parent, children=new_children, type=self.type, symtab=self.symtab)


class StatList(Stat):
    def __init__(self, parent=None, children=None, type=None, symtab=None):
        log_indentation(bold(f"New StatList Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        if children:
            self.children = children
            for child in children:
                child.parent = self
        else:
            self.children = []

        self.type = type

    def append(self, elem):
        elem.parent = self
        log_indentation(f"Appending statement {id(elem)} of type {elem.type_repr()} to StatList {id(self)}")
        self.children.append(elem)

    def get_content(self):
        content = f"Recap StatList {id(self)}: [\n"
        for n in self.children:
            content += ii(f"{n.type_repr()}, {id(n)};\n")
        content += "]"
        return content

    def lower(self):
        instrl = ir.InstructionList(children=self.children, symtab=self.symtab)
        try:
            return self.parent.replace(self, instrl)
        except AttributeError as e:
            if e.name == "replace":  # parent is a ir.Block
                instrl.parent = self.parent
                self.parent.body = instrl
                return True
            else:
                raise e

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return StatList(parent=self.parent, children=new_children, type=self.type, symtab=self.symtab)
