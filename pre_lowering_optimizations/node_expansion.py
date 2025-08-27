#!/usr/bin/env python3

"""Sometimes, during parsing, we can't exactly create the high-level nodes
structure that we want, but at the same time, we can't always relay on low-
level nodes; in this stage, we traverse the IR tree multiple times and we
expand high-level nodes using other high-level nodes"""

from ir import CallStat, AssignStat, PointerType, new_temporary


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
        if self.returns[i] == "_":
            i += 1
            continue

        # return by reference, change arrays into pointers
        type = function_returns[i].stype
        if function_returns[i].is_array():
            type = PointerType(type.basetype)

        # TODO: offset?
        temp = new_temporary(self.symtab, type)
        assign_stat = AssignStat(parent=self.parent, target=self.returns[i], offset=None, expr=temp, symtab=self.symtab)
        assign_stats.append(assign_stat)

    # add the assign statements after the call
    index = self.parent.children.index(self)
    for assign_stat in assign_stats:
        self.parent.children.insert(index + 1, assign_stat)
        index += 1

    # these temporaries are the ones that will contain the return values
    self.returns_storage = {x.symbol: x.expr for x in assign_stats}


CallStat.expand = add_return_assignments


def node_expansion(node):
    try:
        node.expand()
    except AttributeError as e:
        if not str(e).endswith("has no attribute 'expand'"):
            raise RuntimeError(f"Raised AttributeError {e}")


def perform_node_expansion(program):
    program.navigate(node_expansion, quiet=True)
