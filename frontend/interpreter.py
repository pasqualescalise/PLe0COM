#!/usr/bin/env python3

"""Abstract Syntax Tree Interpreter

Instead of optimizing and compiling the AST, we just walk it and interpret
every ASTNode; to maximize compatibility with the compiler, this interpreter
assumes 32 bit integers and makes them overflow or underflow
"""

from copy import deepcopy

from frontend.ast import Const, Var, ArrayElement, String, BinaryExpr, UnaryExpr, CallStat, IfStat, WhileStat, ForStat, AssignStat, PrintStat, ReadStat, ReturnStat, StatList
from ir.ir import FunctionDef, PointerType, TYPENAMES
from ir.function_tree import FunctionTree


RETURN_FLAG = False


# Since we expect 32/16/8 bit numbers, apply a mask to them,
# and consider the sign if they are not unsigned
def mask_number_to_its_type(value, type):
    if not type.is_numeric() or isinstance(type, PointerType):
        return value

    match type:
        case x if x == TYPENAMES['int'] or x == TYPENAMES['uint']:  # no distinction
            if value > -4294967296 and value < 4294967295:
                return value

            mask = 0xffffffff
            return value & mask
        case x if x == TYPENAMES['short']:
            if value > -65536 and value < 65535:
                return value

            mask = 0xffff
            return value & mask
        case x if x == TYPENAMES['byte']:
            if value > -128 and value < 127:
                return value

            mask = 0xff
            return value & mask
        case x if x == TYPENAMES['ushort']:
            mask = 0xffff

            return value & mask
        case x if x == TYPENAMES['ubyte']:
            mask = 0xff

            return value & mask


def const_interpret(self, variable_state):
    if self.value == 'True':
        return True
    elif self.value == 'False':
        return False
    else:
        return self.value


Const.interpret = const_interpret


def var_interpret(self, variable_state):
    if self.offset is None:
        return mask_number_to_its_type(variable_state[self.symbol], self.type)

    indexes = self.offset.interpret(variable_state)
    element = variable_state[self.symbol]
    for index in indexes:
        element = element[index]

    return mask_number_to_its_type(element, self.type)


Var.interpret = var_interpret


# XXX: normally this returns an element of the array, but for the
#      interpreter it's easier to return a list of indexes
def array_element_interpret(self, variable_state):
    indexes = []
    for index in self.children:
        indexes.append(index.interpret(variable_state))

    return indexes


ArrayElement.interpret = array_element_interpret


def string_interpret(self, variable_state):
    # convert \x to x (eg. \n to an actual newline)
    return self.value.encode('raw_unicode_escape').decode('unicode_escape')


String.interpret = string_interpret


def binary_expr_interpret(self, variable_state):
    op_a = self.children[1].interpret(variable_state)
    op_b = self.children[2].interpret(variable_state)

    match self.children[0]:
        case 'plus':
            return mask_number_to_its_type(op_a + op_b, self.type)
        case 'minus':
            return mask_number_to_its_type(op_a - op_b, self.type)
        case 'times':
            return mask_number_to_its_type(op_a * op_b, self.type)
        case 'slash':
            # XXX: we only do integer divisions now
            return mask_number_to_its_type(op_a // op_b, self.type)
        case 'shl':
            return mask_number_to_its_type(op_a << op_b, self.type)
        case 'shr':
            return mask_number_to_its_type(op_a >> op_b, self.type)
        case 'mod':
            return mask_number_to_its_type(op_a % op_b, self.type)

        case 'eql':
            return op_a == op_b
        case 'neq':
            return op_a != op_b
        case 'lss':
            return op_a < op_b
        case 'leq':
            return op_a <= op_b
        case 'gtr':
            return op_a > op_b
        case 'geq':
            return op_a >= op_b

        case 'and':
            return op_a and op_b
        case 'or':
            return op_a or op_b


BinaryExpr.interpret = binary_expr_interpret


def unary_expr_interpret(self, variable_state):
    op = self.children[1].interpret(variable_state)

    match self.children[0]:
        case 'plus':
            return mask_number_to_its_type(+op, self.type)
        case 'minus':
            return mask_number_to_its_type(-op, self.type)

        case 'odd':
            return False if op % 2 == 0 else True
        case 'not':
            return not op


UnaryExpr.interpret = unary_expr_interpret


def call_stat_interpret(self, variable_state):
    called_function = FunctionTree.get_function_definition(self.function_symbol)

    parameters = {}
    for i in range(len(called_function.parameters)):
        parameters[called_function.parameters[i]] = self.children[i].interpret(variable_state)

    # we don't want to change the actual variable state, so we use
    # this copy to pass parameters and get return values
    function_variable_state = variable_state | parameters
    called_function.interpret(function_variable_state)

    global RETURN_FLAG
    RETURN_FLAG = False

    # get parent variables changed in the children function
    for symbol in variable_state.keys():
        if symbol not in parameters:  # for recursive functions, don't update the current function parameters
            variable_state[symbol] = function_variable_state[symbol]

    j = 0  # skip dontcares
    for i in range(len(called_function.returns)):
        if self.returns[i] != '_':
            variable_state[self.returns_storage[j]] = mask_number_to_its_type(function_variable_state[called_function.returns[i]], self.returns_storage[j].type)
            j += 1


CallStat.interpret = call_stat_interpret


def if_stat_interpret(self, variable_state):
    if self.cond.interpret(variable_state):
        self.thenpart.interpret(variable_state)
        return

    for i in range(len(self.children)):  # elifs conditions
        if self.children[i].interpret(variable_state):
            self.elifspart.children[i].interpret(variable_state)
            return

    if self.elsepart is not None:
        self.elsepart.interpret(variable_state)


IfStat.interpret = if_stat_interpret


def while_stat_interpret(self, variable_state):
    while self.cond.interpret(variable_state):
        self.body.interpret(variable_state)


WhileStat.interpret = while_stat_interpret


def for_stat_interpret(self, variable_state):
    self.init.interpret(variable_state)

    while self.cond.interpret(variable_state):
        self.body.interpret(variable_state)
        self.step.interpret(variable_state)

    if self.epilogue is not None:
        self.epilogue.interpret(variable_state)


ForStat.interpret = for_stat_interpret


def assign_stat_interpret(self, variable_state):
    remove_after_assignment = False

    try:
        interpreted_expr = mask_number_to_its_type(self.expr.interpret(variable_state), self.symbol.type)
    except AttributeError as e:
        if e.name == "interpret":  # expr is a Symbol
            interpreted_expr = mask_number_to_its_type(variable_state[self.expr], self.symbol.type)
            remove_after_assignment = True
        else:
            raise e

    if self.offset is None:
        variable_state[self.symbol] = interpreted_expr
    else:
        indexes = self.offset.interpret(variable_state)
        element = variable_state[self.symbol]
        for index in indexes[:-1]:
            element = element[index]

        element[indexes[-1]] = interpreted_expr

    # to avoid polluting the variable state, remove the Symbol
    # used only for this assignment
    if remove_after_assignment:
        del variable_state[self.expr]


AssignStat.interpret = assign_stat_interpret


def print_stat_interpret(self, variable_state):
    interpreted_expr = self.children[0].interpret(variable_state)

    # print negative signed numbers as negative
    if self.print_type.is_numeric() and ('unsigned' not in self.print_type.qualifiers or self.print_type == TYPENAMES['uint']) and interpreted_expr > 0:
        mask = (2 ** self.print_type.size) - 1
        if interpreted_expr & mask > mask // 2:
            interpreted_expr = (2 ** self.print_type.size) - interpreted_expr
            interpreted_expr *= -1

    global OUTPUT
    OUTPUT += str(interpreted_expr)

    if self.newline:
        OUTPUT += "\n"


PrintStat.interpret = print_stat_interpret


def read_stat_interpret(self, variable_state):  # TODO: this is not in use now
    return int(input())


ReadStat.interpret = read_stat_interpret


def return_stat_interpret(self, variable_state):
    returns = [x.interpret(variable_state) for x in self.children]
    function_returns = self.get_function().returns

    for i in range(len(returns)):
        variable_state[function_returns[i]] = returns[i]

    global RETURN_FLAG
    RETURN_FLAG = True


ReturnStat.interpret = return_stat_interpret


def stat_list_interpret(self, variable_state):
    for statement in self.children:
        if RETURN_FLAG:
            return
        statement.interpret(variable_state)


StatList.interpret = stat_list_interpret


def get_default_value(type):  # TODO: could this be integrated in Type()?
    match type:
        case x if x.is_numeric():
            return 0
        case x if x == TYPENAMES["char"]:
            return ""
        case x if x == TYPENAMES["boolean"]:
            return False


def functiondef_interpret(self, variable_state):
    for symbol in self.body.symtab:
        if symbol in variable_state.keys():
            continue
        elif symbol.is_string():
            variable_state[symbol] = get_default_value(symbol.type.basetype)
        elif symbol.is_array():
            if symbol.type.basetype == TYPENAMES["char"]:
                # treat them as string arrays, not char arrays
                variable_state[symbol] = [get_default_value(symbol.type.basetype) for x in range(symbol.type.dims[-2])]
                for dim in list(reversed(symbol.type.dims[:-2])):
                    variable_state[symbol] = [deepcopy(variable_state[symbol]) for x in range(dim)]
            else:
                variable_state[symbol] = [get_default_value(symbol.type.basetype) for x in range(symbol.type.dims[-1])]
                for dim in list(reversed(symbol.type.dims[:-1])):
                    variable_state[symbol] = [deepcopy(variable_state[symbol]) for x in range(dim)]
        elif 'assignable' not in symbol.type.qualifiers:
            continue
        else:
            variable_state[symbol] = get_default_value(symbol.type)

    self.body.body.interpret(variable_state)


FunctionDef.interpret = functiondef_interpret


def perform_interpretation(program):
    global OUTPUT
    OUTPUT = ""

    variable_state = {}
    program.interpret(variable_state)

    return OUTPUT
