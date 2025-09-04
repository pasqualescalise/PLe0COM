#!/usr/bin/env python3

"""Helper functions used by the code generator"""

from function_tree import FunctionTree, get_distance_between_functions
from regalloc import RegisterAllocation
from logger import ii, black, blue, cyan, bold, italic

REG_FP = 11
REG_SCRATCH = 12
REG_SP = 13
REG_LR = 14
REG_PC = 15

REGS_CALLEESAVE = [4, 5, 6, 7, 8, 9, 10]
REGS_CALLERSAVE = [0, 1, 2, 3]

REGISTER_SIZE = 32

# each time a call gets made, the caller saved and the callee saved registers
# gets pushed on the stack, + the current frame pointer and return pointer
CALL_OFFSET = (len(REGS_CALLEESAVE) + len(REGS_CALLERSAVE) + 2) * 4
CALLEE_OFFSET = (len(REGS_CALLEESAVE) + 2) * 4


def get_register_string(regid):
    if regid == REG_LR:
        return bold("lr")
    elif regid == REG_SP:
        return bold("sp")
    return bold(f"r{regid}")


def save_regs(reglist):
    if len(reglist) == 0:
        return ''

    res = ii(f"{cyan('push')} " + "{")
    for i in range(0, len(reglist)):
        if i > 0:
            res += ", "
        res += get_register_string(reglist[i])
    res += "}\n"
    return res


def restore_regs(reglist):
    if len(reglist) == 0:
        return ''

    res = ii(f"{cyan('pop')} " + "{")
    for i in range(0, len(reglist)):
        if i > 0:
            res += ", "
        res += get_register_string(reglist[i])
    res += "}\n"
    return res


def comment(cont):
    return black(f"@ {cont}\n")


# Returns code that loads into REG_SCRATCH the frame pointer of the static
# parent of the function we are calling (static chain pointer)
def load_static_chain_pointer(call):
    if call.parent.parent.parent is not None:
        calling_function = FunctionTree.get_function_node(call.parent.parent.parent.symbol)
    else:
        calling_function = FunctionTree.root
    called_function = FunctionTree.get_function_node(call.target)

    distance = get_distance_between_functions(calling_function, called_function)

    res = ""

    match distance:
        case (1, 0):  # child function, pass our own frame pointer
            res += ii(f"{blue('mov')} {get_register_string(REG_SCRATCH)}, {get_register_string(REG_FP)}\n")

        case (0, 0) | (0, 1):  # recursion or sibling function, pass the frame pointer of the parent
            res += ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, [{get_register_string(REG_FP)}, #{italic(-4)}]")
            res += ii(f"{comment(f'passing frame pointer of parent function {called_function.parent.symbol.name}')}")

        case (x, _) if x < 0:  # (grand)parent/uncle function, pass the frame pointer of the parent of that function
            res += ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, [{get_register_string(REG_FP)}, #{italic(-4)}]\n")
            for i in range(-x):  # keep loading parent frame pointers until we find the correct one
                res += ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, [{get_register_string(REG_SCRATCH)}, #{italic(-4)}]\n")
            res = res[:-1]
            res += ii(f"{comment(f'passing frame pointer of parent function {called_function.parent.symbol.name}')}")

        case _:
            raise RuntimeError(f"Can't call function {call.target} from function {calling_function.symbol}")  # XXX: this should not be possible

    return res


# Returns code that loads into REG_SCRATCH the frame pointer of the static
# parent of the function we are calling (static chain pointer): this is
# needed only if we are trying to access a symbol of a (grand)parent function
def access_static_chain_pointer(node, symbol):
    node_function = FunctionTree.get_function_node(node.parent.parent.parent.symbol)
    symbol_function = FunctionTree.get_function_node(symbol.function_symbol)

    # trying to access a symbol not defined in the current function
    if symbol_function.symbol != node_function.symbol:
        distance = get_distance_between_functions(node_function, symbol_function)

        match distance:
            case (x, 0) if x < 0:  # we are trying to access a variable stored in a (grand)parent
                res = ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, [{get_register_string(REG_FP)}, #{italic(-4)}]\n")
                for i in range(-x - 1):  # keep loading parent frame pointers until we find the correct one
                    res += ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, [{get_register_string(REG_SCRATCH)}, #{italic(-4)}]\n")

            # XXX: these should not be possible
            case (x, _) if x > 0:
                raise RuntimeError("Trying to access a variable from a child function")
            case (_, y) if y != 0:
                raise RuntimeError("Trying to access a variable from an (grand)auncle function")
            case _:
                raise RuntimeError(f"Can't access variable {symbol.name} from function {node_function.symbol}")

        res = res[:-1]
        res += ii(f"{comment(f'accessing frame pointer of parent function {symbol_function.symbol.name}')}")
        return res

    return ""


def enter_function_body(self, block):
    self.spillvarloc = dict()
    self.spillvarloctop = -block.stackroom


def gen_spill_load_if_necessary(self, var):
    self.dematerialize_spilled_var_if_necessary(var)
    if not self.materialize_spilled_var_if_necessary(var):
        # not a spilled variable
        return ''

    offs = self.spillvarloctop - self.vartospillframeoffset[var] - 4
    rd = self.get_register_for_variable(var)
    res = ii(f"{blue('ldr')} {rd}, [{get_register_string(REG_FP)}, #{italic(f'{offs}')}]")
    res += ii(f"{comment('fill')}")
    return res


def get_register_for_variable(self, var):
    self.materialize_spilled_var_if_necessary(var)
    res = get_register_string(self.var_to_reg[var])
    return res


def gen_spill_store_if_necessary(self, var):
    if not self.materialize_spilled_var_if_necessary(var):
        # not a spilled variable
        return ''

    offs = self.spillvarloctop - self.vartospillframeoffset[var] - 4
    rd = self.get_register_for_variable(var)
    res = ii(f"{blue('str')} {rd}, [{get_register_string(REG_FP)}, #{italic(f'{offs}')}]")
    res += ii(f"{comment('spill')}")
    self.dematerialize_spilled_var_if_necessary(var)
    return res


RegisterAllocation.enter_function_body = enter_function_body
RegisterAllocation.gen_spill_load_if_necessary = gen_spill_load_if_necessary
RegisterAllocation.get_register_for_variable = get_register_for_variable
RegisterAllocation.gen_spill_store_if_necessary = gen_spill_store_if_necessary
