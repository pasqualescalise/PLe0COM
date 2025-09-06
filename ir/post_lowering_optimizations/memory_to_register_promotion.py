#!/usr/bin/env python3

"""It's faster to access the registers than the stack: move allowed
variables in registers instead of the stack"""

from ir.ir import StoreStat, ArrayType, PointerType
from backend.codegenhelp import REGISTER_SIZE
from logger import red, green, blue


# Remove the symbol from the symbol table and convert it to a register
def promote_symbol(symbol, root):
    instructions = root.body.children

    root.symtab.remove(symbol)
    symbol.alloct = 'reg'

    for i in range(0, len(instructions)):
        if isinstance(instructions[i], StoreStat) and instructions[i].dest == symbol:
            instructions[i].killhint = symbol


# A variable can be promoted from being stored in memory to being stored in a register if
#   - the variable is not used in any nested procedure
#   - the variable address is needed for something (example -> ArrayType, PointerType)
#   - the symbol type is not the same size as the registers
def memory_to_register_promotion(root):
    to_promote = []

    for symbol in root.symtab:
        if symbol.stype.size <= 0:
            continue

        if symbol.alloct not in ['auto', 'global']:
            continue

        try:
            if symbol.checked:
                continue
        except AttributeError:
            symbol.checked = True

        print(f"{blue('SYMBOL:')} {symbol}")

        if isinstance(symbol.stype, ArrayType) or isinstance(symbol.stype, PointerType):
            print(red("Can't promote because the symbol address needs to be accessible\n"))
            continue

        if symbol.used_in_nested_procedure:
            print(red("Can't promote because the symbol is used in a nested procedure\n"))
            continue

        if symbol.stype.size != REGISTER_SIZE:
            print(red("Can't promote because the symbol is not the same size as the registers\n"))
            continue

        print(green("Promoted\n"))
        to_promote.append(symbol)

    for symbol in to_promote:
        promote_symbol(symbol, root)

    for function_definition in root.defs.children:
        memory_to_register_promotion(function_definition.body)
