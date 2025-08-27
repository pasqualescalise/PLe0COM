#!/usr/bin/env python3

"""Data layout computation pass. For each symbol whose location (alloct)
is not a register, calculate their position. Symbols can be allocated
either in the data section (alloct data or alloct global) or in the
local stack frame (alloct auto, alloct param)

Function parameters exist only in the called function and its nested
children, and are also referenced using stack offset (even though some
of them are passed in registers)"""

from codegenhelp import CALLEE_OFFSET, REGISTER_SIZE
from logger import cyan
from ir import DataSymbolTable, ArrayType


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


# Calculate the offset of all the variables in the stack, including parameters
def perform_data_layout_of_function(funcroot):
    offs = 0
    fname = funcroot.symbol.name

    # local variables
    for var in funcroot.body.symtab.exclude_alloct(['reg', 'global', 'param', 'return', 'data']):
        if var.stype.size == 0:
            continue

        if var.allocinfo is not None:  # nested functions
            continue

        bsize = var.stype.size // 8
        padding = 4 - bsize

        name = f"_l_{fname}_{var.name}"
        offs -= bsize + padding
        var.set_alloc_info(LocalSymbolLayout(name, offs, bsize))

    # how much space to reserve to local variables
    funcroot.body.stackroom = -offs

    negative_offs = offs
    positive_offs = CALLEE_OFFSET - 4

    # parameters: the first 4 get pushed after the FP (negative offset) while the other
    # are before the FP (positive offset)
    for i in range(len(funcroot.parameters) - 1, -1, -1):
        parameter = funcroot.parameters[i]
        name = f"_p_{fname}_{parameter.name}"
        bsize = parameter.stype.size // 8  # in byte

        if isinstance(parameter.stype, ArrayType):  # pass by reference
            bsize = REGISTER_SIZE // 8

        padding = 4 - bsize
        if i < 4:
            negative_offs -= bsize + padding
            parameter.set_alloc_info(LocalSymbolLayout(name, negative_offs, bsize))
        else:
            positive_offs += bsize + padding
            parameter.set_alloc_info(LocalSymbolLayout(name, positive_offs, bsize))

    print(f"{cyan(f'{funcroot.symbol.name}')} {funcroot.body.symtab}")

    for defin in funcroot.body.defs.children:
        perform_data_layout_of_function(defin)


# Calculate the size of all the global variables
def perform_data_layout_of_program(root):
    for var in root.symtab.exclude_alloct(['reg', 'data']):
        if var.stype.size == 0:
            continue

        bsize = var.stype.size // 8  # in byte

        name = f"_g_main_{var.name}"
        var.set_alloc_info(GlobalSymbolLayout(name, bsize))

    print(f"{cyan('main')} {root.symtab}")


def perform_data_layout_of_data_variables():
    for symbol in DataSymbolTable.get_data_symtab():
        symbol.set_alloc_info(GlobalSymbolLayout(symbol.name, symbol.stype.size // 8))
