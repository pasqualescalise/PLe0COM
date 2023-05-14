#!/usr/bin/env python3

"""Data layout computation pass. Each symbol whose location (alloct)
is not a register, is allocated in the local stack frame (LocalSymbol) or in
the data section of the executable (GlobalSymbol)."""


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


def perform_data_layout(root):
    perform_data_layout_of_program(root)
    for defin in root.defs.children:
        perform_data_layout_of_function(defin)


# XXX: this works if we assume all parameters of the same bsize
def perform_data_layout_of_function(funcroot):
    offs = 0  # prev fp
    fixed_param_offs = 48
    fixed_returns_offs = 48

    # need to keep track of function called to perfectly allocate return values and parameters
    current_function = None
    if len(funcroot.body.symtab) > 0:
        current_function = funcroot.body.symtab[0].fname

    for var in funcroot.body.symtab:
        if var.stype.size == 0:
            continue

        bsize = var.stype.size // 8

        if var.alloct == 'param':
            # parameters are before the returns in the symbol table
            # each time a new function is introduced reset the offset for the returns
            if var.fname == current_function:
                fixed_returns_offs += bsize
            else:
                fixed_returns_offs = 48 + bsize + bsize * var.offset

            prefix = "_p_" + funcroot.symbol.name + "_" + var.fname + "_"
            param_offs = fixed_param_offs + bsize + bsize * var.offset
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, param_offs , bsize))

        elif var.alloct == 'return':
            prefix = "_r_" + var.fname + "_" + funcroot.symbol.name + "_"
            returns_offs = fixed_returns_offs + bsize + bsize * var.offset
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, returns_offs , bsize))

        else:
            prefix = "_l_" + funcroot.symbol.name + "_"
            offs -= bsize
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, offs, bsize))

    # XXX: added myself
    for defin in funcroot.body.defs.children:
        perform_data_layout_of_function(defin)

    funcroot.body.stackroom = -offs


# XXX: this works if we assume all parameters of the same bsize
# the parameters and the returns are of functions called by the main, so they behave exactly like other functions
def perform_data_layout_of_program(root):
    fixed_param_offs = 48
    fixed_returns_offs = 48

    # need to keep track of function called to perfectly allocate return values and parameters
    current_function = None
    if len(root.symtab) > 0:
        current_function = root.symtab[0].fname

    for var in root.symtab:
        if var.stype.size == 0:
            continue

        bsize = var.stype.size // 8

        if var.alloct == 'param':
            # parameters are before the returns in the symbol table
            # each time a new function is introduced reset the offset for the returns
            if var.fname == current_function:
                fixed_returns_offs += bsize
            else:
                fixed_returns_offs = 48 + bsize + bsize * var.offset

            prefix = "_p_main_" + var.fname + "_"
            param_offs = fixed_param_offs + bsize + bsize * var.offset
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, param_offs , bsize))

        elif var.alloct == 'return':
            prefix = "_r_" + var.fname + "_main_"
            returns_offs = fixed_returns_offs + bsize + bsize * var.offset
            var.set_alloc_info(LocalSymbolLayout(prefix + var.name, returns_offs , bsize))

        else:
            prefix = "_g_"
            var.set_alloc_info(GlobalSymbolLayout(prefix + var.name, bsize))
