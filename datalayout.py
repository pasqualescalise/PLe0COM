#!/usr/bin/env python3

"""Data layout computation pass. Each symbol whose location (alloct)
is not a register, is allocated in the local stack frame (LocalSymbol) or in
the data section of the executable (GlobalSymbol)."""

from codegenhelp import CALL_OFFSET
from ir import *


class SymbolLayout(object):
    def __init__(self, symname, bsize):
        self.symname = symname
        self.bsize = bsize


class LocalSymbolLayout(SymbolLayout):
    def __init__(self, symname, fpreloff, bsize):
        self.symname = symname
        self.fpreloff = fpreloff
        self.bsize = bsize

    def __repr__(self):
        return self.symname + ": fp + (" + repr(self.fpreloff) + ") [def byte " + \
               repr(self.bsize) + "]"


class GlobalSymbolLayout(SymbolLayout):
    def __init__(self, symname, bsize):
        self.symname = symname
        self.bsize = bsize

    def __repr__(self):
        return self.symname + ": def byte " + repr(self.bsize)


# remove the symbol from the symbol table and convert it to a register
def promote_symbol(symbol, root):
    instructions = root.body.children

    root.symtab.remove(symbol)
    symbol.alloct = 'reg'

    for i in range(0, len(instructions)):
        if type(instructions[i]) is StoreStat and instructions[i].dest == symbol:
            instructions[i].killhint = symbol

# a variable can be promoted from being stored in memory to being stored in a register if
#   - the variable is not used in any nested procedure
def perform_memory_to_register_promotion(root):
    instructions = root.body.children
    to_promote = []

    for symbol in root.symtab:
        if symbol.alloct not in ['auto', 'global'] and symbol.stype.size > 0:
            continue

        print("SYMBOL: " + repr(symbol))

        if symbol.used_in_nested_procedure:
            print("Can't promote because the symbol is used in a nested procedure\n\n")
            continue

        print("Promoted\n\n")
        to_promote.append(symbol)

    for symbol in to_promote:
        promote_symbol(symbol, root)

    for function_definition in root.defs.children:
        perform_memory_to_register_promotion(function_definition.body)

def perform_data_layout(root):
    perform_data_layout_of_program(root)
    for defin in root.defs.children:
        perform_data_layout_of_function(defin)

def perform_data_layout_of_function(funcroot):
    offs = 0  # prev fp
    # considering all the caller and callee saved registers
    minimum_fixed_offset = CALL_OFFSET - 4
    param_offs = minimum_fixed_offset
    returns_offs = minimum_fixed_offset

    # need to keep track of the function called to perfectly allocate return values and parameters
    current_function = None
    if len(funcroot.body.symtab) > 0:
        current_function = funcroot.body.symtab[0].fname

    for var in funcroot.body.symtab:
        if var.stype.size == 0:
            continue

        bsize = var.stype.size // 8

        if var.alloct == 'param':
            # parameters are before the returns in the symbol table
            # each time a new function is introduced reset the offset
            if var.fname == current_function:
                returns_offs += bsize
            else:
                returns_offs = minimum_fixed_offset + bsize
                param_offs = minimum_fixed_offset
                current_function = var.fname

            prefix = "_p_" + funcroot.symbol.name + "_" + var.fname + "_"
            param_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, param_offs , bsize))

        elif var.alloct == 'return':
            prefix = "_r_" + var.fname + "_" + funcroot.symbol.name + "_"
            returns_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, returns_offs , bsize))

        else:
            prefix = "_l_" + funcroot.symbol.name + "_"
            offs -= bsize
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, offs, bsize))

    funcroot.body.stackroom = -offs

    # XXX: added myself
    for defin in funcroot.body.defs.children:
        perform_data_layout_of_function(defin)

# the parameters and the returns are of functions called by the main, so they behave exactly like other functions
def perform_data_layout_of_program(root):
    # considering all the caller and callee saved registers
    minimum_fixed_offset = CALL_OFFSET - 4
    param_offs = minimum_fixed_offset
    returns_offs = minimum_fixed_offset

    # need to keep track of the function called to perfectly allocate return values and parameters
    current_function = None
    if len(root.symtab) > 0:
        current_function = root.symtab[0].fname

    for var in root.symtab:
        if var.stype.size == 0:
            continue

        bsize = var.stype.size // 8

        if var.alloct == 'param':
            # parameters are before the returns in the symbol table
            # each time a new function is introduced reset the offset
            if var.fname == current_function:
                returns_offs += bsize
            else:
                returns_offs = minimum_fixed_offset + bsize
                param_offs = minimum_fixed_offset
                current_function = var.fname

            prefix = "_p_main_" + var.fname + "_"
            param_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, param_offs , bsize))

        elif var.alloct == 'return':
            prefix = "_r_" + var.fname + "_main_"
            returns_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, returns_offs , bsize))

        else:
            prefix = "_g_"
            var.set_alloc_info(GlobalSymbolLayout(prefix + var.name, bsize))
