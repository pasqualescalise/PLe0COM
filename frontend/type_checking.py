#!/usr/bin/env python3

"""Navigate through the Abstract Syntax Tree, assigning types to all ASTNodes:
leaves (e.g. Vars) and Expressions have their own type, while Statements have
the 'statement' type; for statements, check that types are respected (e.g. only
print printable stuff, call with the right arguments, ...)"""

from frontend.ast import Const, Var, ArrayElement, String, StaticArray, BinaryExpr, UnaryExpr, CallStat, IfStat, WhileStat, ForStat, AssignStat, PrintStat, ReadStat, ReturnStat, StatList, UNARY_CONDITIONALS, BINARY_CONDITIONALS, UNARY_BOOLEANS, BINARY_BOOLEANS
from ir.function_tree import FunctionTree
from ir.ir import FunctionDef, ArrayType, TYPENAMES
from logger import log_indentation, green, underline


def non_strict_type_equivalence(type_a, type_b):
    if type_a == type_b:
        return True

    elif type_a.is_numeric() and type_b.is_numeric():
        return True

    elif type_a.is_string() and type_b.is_string():
        if type_a.size > type_b.size:  # we can always put a smaller string in a bigger one
            return True

    elif type_a.is_array() and type_b.is_array():
        if type_a.basetype != type_b.basetype:
            return False

        return True  # we don't care about their size

    return False


# Returns the type of the symbol:
#  * if it's scalar (offset is None) -> symbol type
#  * if it's an array -> consider how many times we are accessing it
#    e.g. if we access one time, arr[2][2] becomes arr[2]
def symbol_with_offset_type(symbol, offset):
    num_of_accesses = len(offset.children)

    if offset is None:
        return symbol.type

    dims = symbol.type.dims[num_of_accesses:]
    if dims != []:
        return ArrayType(None, dims, symbol.type.basetype)
    else:
        return symbol.type.basetype


def const_type_checking(self):
    if self.symbol is not None:
        self.type = self.symbol.type

    match self.value:
        case "True" | "False":
            self.type = TYPENAMES['boolean']
        case int():
            self.type = TYPENAMES['int']
        case _:  # XXX: other types never happen now
            raise TypeError(f"Can't compute type of Const {self.id}")


Const.type_checking = const_type_checking


def var_type_checking(self):
    if self.symbol is None:
        raise TypeError(f"Can't compute type of Var {self.id} since it doesn't have a symbol")

    self.type = self.symbol.type

    if self.offset is not None:
        self.type = self.offset.type


Var.type_checking = var_type_checking


def array_element_type_checking(self):
    if self.symbol is None:
        raise TypeError(f"Can't compute type of ArrayElement {self.id} since it doesn't have a symbol")

    elif self.children == [] or not self.symbol.is_array():
        raise TypeError("Can only index array variables")

    for index in self.children:
        if not index.type.is_numeric():
            raise TypeError("Array indexes must be numeric")

    self.type = symbol_with_offset_type(self.symbol, self)


ArrayElement.type_checking = array_element_type_checking


def string_type_checking(self):
    self.type = ArrayType(None, [len(self.value) + 1], TYPENAMES['char'])


String.type_checking = string_type_checking


# XXX: this gets called not during normal type checking but during parsing,
#      since StaticArrays don't exist after node expansion
def static_array_type_checking(self):
    if isinstance(self.values_type, ArrayType):
        self.type = ArrayType(None, [len(self.values)] + self.values_type.dims, self.values_type.basetype)
    else:
        self.type = ArrayType(None, [len(self.values)], self.values_type)

    for value in self.values:
        value.navigate(type_checking, quiet=True)  # need to manually do this

        if non_strict_type_equivalence(self.values_type, value.type):
            continue

        raise TypeError(f"All values of static array {id(self)} must be of type {self.values_type} but value {id(value)} is of type {value.type}")


StaticArray.type_checking = static_array_type_checking


def binary_expr_type_checking(self):
    type_a = self.children[0].type
    type_b = self.children[1].type

    self.mask = False  # wheter to apply a mask to one operand

    if type_a == type_b:
        self.type = TYPENAMES[type_a.name]

    elif type_a.is_numeric() and type_b.is_numeric():  # apply a mask to the smallest operand
        biggest_type = type_a if type_a.size > type_b.size else type_b
        self.mask = True
        self.type = TYPENAMES[biggest_type.name]

    else:
        raise TypeError(f"Trying to operate on two factors of different types ({type_a} and {type_b})")

    if ('unsigned' in type_a.qualifiers) and ('unsigned' in type_b.qualifiers):
        self.type.qualifiers += ['unsigned']
    else:
        try:  # signed and unsigned operation, the result must be signed
            self.type.qualifiers.remove('unsigned')
        except ValueError:
            pass

    if self.operator in BINARY_CONDITIONALS:
        self.type = TYPENAMES['boolean']

    elif self.operator in BINARY_BOOLEANS and self.children[1].type != TYPENAMES['boolean']:
        raise TypeError(f"Boolean operation {self.children[0]} can only be applied to unary operators, not {self.children[1].type} and {self.children[2].type}")


BinaryExpr.type_checking = binary_expr_type_checking


def unary_expr_type_checking(self):
    self.type = self.children[0].type

    if self.operator in UNARY_CONDITIONALS:
        self.type = TYPENAMES['boolean']

    elif self.operator in UNARY_BOOLEANS and self.children[0].type != TYPENAMES['boolean']:
        raise TypeError(f"Boolean operation {self.children[0]} can only be applied to unary operators, not {self.children[1].type}")


UnaryExpr.type_checking = unary_expr_type_checking


def call_stat_type_checking(self):
    self.type = TYPENAMES['statement']

    function_definition = FunctionTree.get_function_definition(self.function_symbol)

    call_parameters_types = [x.type for x in self.children]
    function_parameters_types = [x.type for x in function_definition.parameters]

    if len(function_parameters_types) > len(call_parameters_types):
        raise TypeError(f"Not passing enough parameters to function {self.function_symbol.name}")
    elif len(function_parameters_types) < len(call_parameters_types):
        raise TypeError(f"Trying to pass too many parameters to function {self.function_symbol.name}")

    for i in range(len(call_parameters_types)):
        if non_strict_type_equivalence(function_parameters_types[i], call_parameters_types[i]):
            continue

        raise TypeError(f"Calling function {function_definition.symbol.name} with parameters of type {call_parameters_types} while it expects {function_parameters_types}")

    # we need types but we can't navigate to this array TODO: yet
    for ret in self.returns:
        if ret != '_':
            ret.navigate(type_checking)

    call_returns_types = [x.type if x != '_' else '_' for x in self.returns]
    function_returns_types = [x.type for x in function_definition.returns]

    if len(function_returns_types) > len(call_returns_types):
        raise TypeError(f"Not returning enough values from function {self.function_symbol.name}")
    elif len(function_returns_types) < len(call_returns_types):
        raise TypeError(f"Trying to return too many values from function {self.function_symbol.name}")

    for i in range(len(call_returns_types)):
        if call_returns_types[i] == '_':
            continue

        if non_strict_type_equivalence(call_returns_types[i], function_returns_types[i]):
            continue

        raise TypeError(f"Calling function {function_definition.symbol.name} with returns of type {call_returns_types} while it expects {function_returns_types}")


CallStat.type_checking = call_stat_type_checking


def if_stat_type_checking(self):
    self.type = TYPENAMES['statement']

    if self.cond.type != TYPENAMES['boolean']:
        raise TypeError("If condition must be a boolean expression")

    for child in self.children:
        if child.type != TYPENAMES['boolean']:
            raise TypeError("Elifs conditions must be boolean expression")


IfStat.type_checking = if_stat_type_checking


def while_stat_type_checking(self):
    self.type = TYPENAMES['statement']

    if self.cond.type != TYPENAMES['boolean']:
        raise TypeError("While condition must be a boolean expression")


WhileStat.type_checking = while_stat_type_checking


def for_stat_type_checking(self):
    self.type = TYPENAMES['statement']

    if self.cond.type != TYPENAMES['boolean']:
        raise TypeError("While condition must be a boolean expression")


ForStat.type_checking = for_stat_type_checking


def assign_stat_type_checking(self):
    self.type = TYPENAMES['statement']

    if self.offset is not None and not self.symbol.is_array():
        raise TypeError("Trying to access a non-array variable with an offset")

    if self.offset is None:
        left_hand_type = self.symbol.type
    else:
        left_hand_type = self.offset.type
    right_hand_type = self.expr.type

    if non_strict_type_equivalence(left_hand_type, right_hand_type):
        return

    raise TypeError(f"Trying to assign a value of type {right_hand_type} to a variable of type {left_hand_type}")


AssignStat.type_checking = assign_stat_type_checking


def print_stat_type_checking(self):
    self.type = TYPENAMES['statement']

    expr = self.children[0]
    if 'printable' not in expr.type.qualifiers:
        raise TypeError(f"Can't print value of type {expr.type}")

    self.print_type = expr.type


PrintStat.type_checking = print_stat_type_checking


def read_stat_type_checking(self):  # TODO: this is not in use now
    self.type = TYPENAMES['int']


ReadStat.type_checking = read_stat_type_checking


def return_stat_type_checking(self):
    self.type = TYPENAMES['statement']

    function_returns_types = [x.type for x in self.get_function().returns]
    returns_types = [x.type for x in self.children]
    self.masks = []  # wheter to apply a mask to one operand

    if len(function_returns_types) > len(returns_types):
        raise TypeError(f"Trying to return too few values from function {self.get_function().symbol.name}")
    elif len(function_returns_types) < len(returns_types):
        raise TypeError(f"Trying to return too many values from function {self.get_function().symbol.name}")

    for i in range(len(self.children)):
        if returns_types[i].is_array() and not returns_types[i].is_string():
            raise TypeError(f"Can't return an array value from function {self.get_function().symbol}")
        elif returns_types[i].is_pointer() and not returns_types[i].is_string():
            raise TypeError(f"Can't return a pointer value from function {self.get_function().symbol}")

        if non_strict_type_equivalence(function_returns_types[i], returns_types[i]):
            if returns_types[i] != function_returns_types[i]:
                if returns_types[i].is_numeric() and function_returns_types[i].is_numeric():
                    if returns_types[i].size > function_returns_types[i].size:
                        continue  # we can return, for example, a byte as an int

                    # mask numeric types if the one we are returning is bigger than the one the caller expects
                    self.masks.append(i)

        continue

        raise TypeError(f"Trying to return a value of type {returns_types[i]} instead of {function_returns_types[i]}")


ReturnStat.type_checking = return_stat_type_checking


def stat_list_type_checking(self):
    self.type = TYPENAMES['statement']

    for child in self.children:
        if child.type != TYPENAMES['statement']:
            raise TypeError(f"Statement List {id(self)} can only contain statement, not {child.type_repr()} of type {child.type}")


StatList.type_checking = stat_list_type_checking


def functiondef_type_checking(self):
    for ret in self.returns:
        # we can't return arrays or pointers since there is no way yet to allocate them not on the stack
        # XXX: we can return strings since they are allocated globaly
        if ret.is_array() and not ret.is_string():
            raise TypeError(f"Can't return {ret} from function {self.symbol} since it's an array")
        elif ret.is_pointer() and not ret.is_string():
            raise TypeError(f"Can't return {ret} from function {self.symbol} since it's a pointer")


FunctionDef.type_checking = functiondef_type_checking


def type_checking(node, quiet=False):
    try:
        node.type_checking()
        if not quiet:
            log_indentation(green(f"Type checked {node.type_repr()}, {id(node)}: {node.type}"))
    except AttributeError as e:
        if e.name == "type_checking":
            if not quiet:
                log_indentation(underline(f"Type checking not yet implemented for type {node.type_repr()}"))
        else:
            raise RuntimeError(e)


def perform_type_checking(program):
    FunctionTree.navigate(type_checking)
