#!/usr/bin/env python3

"""Sometimes, during parsing, we can't exactly create the high-level nodes
structure that we want, but at the same time, we can't always relay on low-
level nodes; in this stage, we traverse the IR tree multiple times and we
expand high-level nodes using other high-level nodes; expanded nodes are
replaced with their expansion"""

from copy import deepcopy

from frontend.ast import CallStat, AssignStat, StaticArray, Var, Const, PrintStat, ArrayElement, String
from ir.function_tree import FunctionTree
from ir.ir import PointerType, TYPENAMES, new_temporary
from ir.support import get_node_list


# Add AssignStats for each (non-dontcare) return symbol of the CallStat;
# creates an attribute, called "returns_storage", that holds all the temporaries
# that will contain the return values
#
# This must be done here since during parsing we can't access the function
# definition to get its return values, and during lowering we can't create AssignStats
def add_return_assignments(self):
    if len(self.returns) == 0:
        return

    function_returns = FunctionTree.get_function_definition(self.function_symbol).returns
    assign_stats = []
    for i in range(len(self.returns)):
        if self.returns[i] == "_":
            i += 1
            continue

        # return by reference, change arrays into pointers
        type = function_returns[i].type
        if function_returns[i].is_array():
            type = PointerType(type.basetype)

        temp = new_temporary(self.symtab, type)
        # TODO: it would be nice to assign to variables instead of symbols
        assign_stat = AssignStat(parent=self.parent, target=self.returns[i].symbol, offset=self.returns[i].offset, expr=temp, symtab=self.symtab)
        assign_stats.append(assign_stat)

    # add the assign statements after the call
    index = self.parent.children.index(self)
    for assign_stat in assign_stats:
        self.parent.children.insert(index + 1, assign_stat)
        index += 1

    # these temporaries are the ones that will contain the return values
    self.returns_storage = [x.expr for x in assign_stats]


CallStat.expand = add_return_assignments


# Expand the assignment of an arry into a sequence of assignments:
# For example:
#   array := [1, 2, 3]int;
#
# Becomes:
#   array[0] := 1
#   array[1] := 2
#   array[3] := 3
def array_assign(self):
    if not isinstance(self.expr, StaticArray):
        return

    assign_stats = []

    for i in range(len(self.expr.values)):
        index = Const(value=i, symtab=self.symtab)
        if self.offset:
            array_access = deepcopy(self.offset)
            array_access.children.append(index)
            index.parent = array_access
        else:
            array_access = ArrayElement(var=self.symbol, indexes=[index], symtab=self.symtab)
        assign_stat = AssignStat(parent=self.parent, target=self.symbol, expr=self.expr.values[i], offset=array_access, symtab=self.symtab)
        assign_stats += [assign_stat]

    # add the new assign statements instead of this one
    index = self.parent.children.index(self)
    self.parent.children.remove(self)
    for assign_stat in assign_stats:
        self.parent.children.insert(index, assign_stat)
        index += 1


AssignStat.expand = array_assign


# Expand a print of an array into a sequence of prints of all the array elements
def array_print(self):
    if not self.children[0]:
        return

    expr = self.children[0]

    # TODO: move after the check
    stats = [PrintStat(expr=String(value="["), newline=False, symtab=self.symtab)]

    # printing an array directly
    if isinstance(expr, StaticArray):
        newline = self.newline  # set in the parser to True to the outermost StaticArray
        for value in expr.values:
            print_stat = PrintStat(expr=value, newline=False, symtab=self.symtab)
            stats += [print_stat]

            if value != expr.values[-1]:
                stats += [PrintStat(expr=String(value=", "), newline=False, symtab=self.symtab)]

    # printing a variable referencing an array or a subarray
    elif isinstance(expr, Var) and (expr.symbol.is_array() and not expr.symbol.is_string()):
        dims = expr.symbol.type.dims
        if expr.offset is not None:
            if len(expr.offset.children) == len(dims):  # we have done it all
                return
            elif (len(expr.offset.children) == len(dims) - 1) and (expr.symbol.type.basetype == TYPENAMES['char']):  # don't go deeper inside strings
                return

            dim = dims[len(expr.offset.children)]
            newline = self.newline
        else:
            dim = expr.symbol.type.dims[0]
            newline = True

        for i in range(dim):
            index = Const(value=i, symtab=self.symtab)
            if expr.offset is None:
                array_access = ArrayElement(var=expr.symbol, indexes=[], symtab=self.symtab)
            else:
                array_access = deepcopy(expr.offset)
            array_access.children.append(index)
            index.parent = array_access
            var = Var(var=expr.symbol, offset=array_access, symtab=self.symtab)
            stats += [PrintStat(expr=var, newline=False, symtab=self.symtab)]

            if i != dim - 1:
                stats += [PrintStat(expr=String(value=", "), newline=False, symtab=self.symtab)]

    else:
        return

    stats += [PrintStat(expr=String(value="]"), newline=newline, symtab=self.symtab)]

    index = self.parent.children.index(self)
    self.parent.children.remove(self)
    for stat in stats:
        stat.parent = self.parent
        self.parent.children.insert(index, stat)
        index += 1


PrintStat.expand = array_print


def node_expansion(node):
    try:
        if node.expanded:
            return
    except AttributeError:
        try:
            node.expanded = True
            node.expand()
        except AttributeError as e:
            if e.name != "expand":
                raise RuntimeError(f"Raised AttributeError {e}")


# Try to expand the program until everything has been expanded
def perform_node_expansion(program):
    program_size = len(get_node_list(program, quiet=True))
    old_program_size = 0
    while old_program_size < program_size:
        FunctionTree.navigate(node_expansion, quiet=True)

        old_program_size = program_size
        program_size = len(get_node_list(program, quiet=True))
