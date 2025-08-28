#!/usr/bin/env python3

"""Sometimes, during parsing, we can't exactly create the high-level nodes
structure that we want, but at the same time, we can't always relay on low-
level nodes; in this stage, we traverse the IR tree multiple times and we
expand high-level nodes using other high-level nodes"""

from ir import CallStat, AssignStat, PointerType, StaticArray, Var, Const, PrintStat, ArrayElement, new_temporary
from support import get_node_list


# Add AssignStats for each (non-dontcare) return symbol of the CallStat;
# creates an attribute, called "returns_storage", that holds all the temporaries
# that will contain the return values
#
# This must be done here since during parsing we can't access the function
# definition to get its return values, and during lowering we can't create AssignStats
def add_return_assignments(self):
    if len(self.returns) == 0:
        return

    function_returns = self.get_function_definition(self.function_symbol).returns
    assign_stats = []
    for i in range(len(self.returns)):
        if self.returns[i][0] == "_":
            i += 1
            continue

        # return by reference, change arrays into pointers
        type = function_returns[i].stype
        if function_returns[i].is_array():
            type = PointerType(type.basetype)

        temp = new_temporary(self.symtab, type)
        assign_stat = AssignStat(parent=self.parent, target=self.returns[i][0], offset=self.returns[i][1], expr=temp, symtab=self.symtab)
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

    stats = []

    stride = self.expr.values_type.size // 8
    for i in range(len(self.expr.values)):
        assign_stat = AssignStat(target=self.symbol, expr=self.expr.values[i], offset=Const(value=(i * stride), symtab=self.symtab), symtab=self.symtab)
        stats += [assign_stat]

    self.children = stats

    for child in self.children:
        child.parent = self


AssignStat.expand = array_assign


# Expand a print of an array into a sequence of prints of all the array elements
def array_print(self):
    if not self.children[0]:
        return

    stats = []

    # printing an array directly
    if isinstance(self.children[0], StaticArray):
        for value in self.children[0].values:
            print_stat = PrintStat(expr=value, symtab=self.symtab)
            stats += [print_stat]

    # printing a variable referencing an array
    elif isinstance(self.children[0], Var) and self.children[0].symbol.is_array() and not self.children[0].symbol.is_string():
        type = self.children[0].symbol.stype.basetype
        size = self.children[0].symbol.stype.size // type.size

        stride = type.size // 8
        for i in range(size):
            array_access = ArrayElement(var=self.children[0].symbol, offset=Const(value=(i * stride), symtab=self.symtab), symtab=self.symtab)
            print_stat = PrintStat(expr=array_access, symtab=self.symtab)
            stats += [print_stat]
    else:
        return

    self.children = stats

    for child in self.children:
        child.parent = self


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
            if not str(e).endswith("has no attribute 'expand'"):
                raise RuntimeError(f"Raised AttributeError {e}")


# Try to expand the program until everything has been expanded
def perform_node_expansion(program):
    program_size = len(get_node_list(program, quiet=True))
    old_program_size = 0
    while old_program_size < program_size:
        program.navigate(node_expansion, quiet=True)

        old_program_size = program_size
        program_size = len(get_node_list(program, quiet=True))
