#!/usr/bin/env python3

"""Data layout computation pass. Each symbol whose location (alloct)
is not a register, is allocated in the local stack frame (LocalSymbol) or in
the data section of the executable (GlobalSymbol)."""

from codegenhelp import CALL_OFFSET
from logger import cyan
from ir import DataSymbolTable


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
        return f"{self.symname} @ [fp + ({self.fpreloff})], size {self.bsize}"


class GlobalSymbolLayout(SymbolLayout):
    def __init__(self, symname, bsize):
        self.symname = symname
        self.bsize = bsize

    def __repr__(self):
        return f"{self.symname} @ size {self.bsize}"


def perform_data_layout(root):
    perform_data_layout_of_program(root)

    for defin in root.defs.children:
        perform_data_layout_of_function(defin)

    perform_data_layout_of_data_variables()


def perform_data_layout_of_function(funcroot):
    offs = 0  # prev fp
    # considering all the caller and callee saved registers
    minimum_fixed_offset = CALL_OFFSET - 4
    param_offs = minimum_fixed_offset
    returns_offs = minimum_fixed_offset

    # need to keep track of the function called to correctly allocate return values and parameters
    current_function = None
    if len(funcroot.body.symtab) > 0:
        current_function = funcroot.body.symtab[0].fname

    for var in funcroot.body.symtab:
        if var.stype.size == 0:
            continue

        if var.allocinfo is not None:  # TODO: this is needed because SymbolTables are broken, fix them
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

            name = f"_p_{funcroot.symbol.name}_{var.fname}_{var.name}"
            param_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(name, param_offs, bsize))

        elif var.alloct == 'return':
            # if there are no parameters, this restarts the offset counter
            # each time a new function is considered
            if var.fname != current_function:
                returns_offs = minimum_fixed_offset
                current_function = var.fname

            name = f"_r_{var.fname}_{funcroot.symbol.name}_{var.name}"
            returns_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(name, returns_offs, bsize))

        else:
            name = f"_l_{funcroot.symbol.name}_{var.name}"
            offs -= bsize
            var.set_alloc_info(LocalSymbolLayout(name, offs, bsize))

    funcroot.body.stackroom = -offs

    if current_function is not None:
        print(f"{cyan(f'{current_function}')} {funcroot.body.symtab}")

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

        bsize = var.stype.size // 8  # in byte

        if var.alloct == 'param':
            # parameters are before the returns in the symbol table
            # each time a new function is introduced reset the offset
            if var.fname == current_function:
                returns_offs += bsize
            else:
                returns_offs = minimum_fixed_offset + bsize
                param_offs = minimum_fixed_offset
                current_function = var.fname

            name = f"_p_main_{var.fname}_{var.name}"
            param_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(name, param_offs, bsize))

        elif var.alloct == 'return':
            # if there are no parameters, this restarts the offset counter
            # each time a new function is considered
            if var.fname != current_function:
                returns_offs = minimum_fixed_offset
                current_function = var.fname

            name = f"_r_{var.fname}_main_{var.name}"
            returns_offs += bsize
            var.set_alloc_info(LocalSymbolLayout(name, returns_offs, bsize))

        else:
            name = f"_g_{var.name}"
            var.set_alloc_info(GlobalSymbolLayout(name, bsize))

    print(f"{cyan('main')} {root.symtab}")


def perform_data_layout_of_data_variables():
    for symbol in DataSymbolTable.get_data_symtab():
        symbol.set_alloc_info(GlobalSymbolLayout(symbol.name, symbol.stype.size))
