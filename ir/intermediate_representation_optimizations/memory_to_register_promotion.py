#!/usr/bin/env python3

"""It's faster to access the registers than the stack: move allowed
variables in registers instead of the stack"""

from copy import deepcopy

from backend.codegenhelp import REGISTER_SIZE
from logger import red, green, blue


# Remove the symbol from the symbol table and convert it to a register
def promote_symbol(symbol, root):
    root.body.symtab.remove(symbol)
    symbol.alloc_class = 'reg'


# A variable can be promoted from being stored in memory to being stored in a register if
#   - the variable is not used in any nested procedure
#   - the variable address is needed for something (example -> ArrayType, PointerType)
#   - the symbol type is not the same size as the registers
def memory_to_register_promotion(root, debug_info):
    to_promote = []

    for symbol in root.body.symtab:
        if symbol.type.size <= 0:
            continue

        if symbol.alloc_class not in ['auto', 'global']:
            continue

        try:
            if symbol.checked:
                continue
        except AttributeError:
            symbol.checked = True

        print(f"{blue('SYMBOL:')} {symbol}")

        if symbol.is_array() or symbol.is_pointer():
            print(red("Can't promote because the symbol address needs to be accessible\n"))
            continue

        if symbol.used_in_nested_procedure:
            print(red("Can't promote because the symbol is used in a nested procedure\n"))
            continue

        if symbol.type.size != REGISTER_SIZE:
            print(red("Can't promote because the symbol is not the same size as the registers\n"))
            continue

        print(green("Promoted\n"))
        to_promote.append(symbol)

    for symbol in to_promote:
        old_symbol = deepcopy(symbol)
        promote_symbol(symbol, root)
        debug_info['memory_to_register_promotion'] += [(old_symbol, (deepcopy(symbol)))]

    for function_definition in root.body.defs.children:
        memory_to_register_promotion(function_definition, debug_info)
