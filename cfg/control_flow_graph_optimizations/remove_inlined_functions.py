#!/usr/bin/env python3

"""Using reference counting, removed useless inlined functions;
this is done after the CFG so that the original code is still checked"""

from ir.ir import DefinitionList
from logger import green, magenta


def remove_inlined_functions(self):
    definition_list = DefinitionList(parent=self.parent)

    for definition in self.children:
        if definition.called_by_counter < 1:
            for sub_definition in definition.body.defs.children:  # move the not inlined definitions upwards
                if sub_definition.called_by_counter > 0:
                    definition_list.append(sub_definition)

            print(f"{green('Removed inlined function')} {magenta(f'{definition.symbol.name}')}")
        else:
            definition_list.append(definition)
    self.parent.defs = definition_list


DefinitionList.remove_inlined_functions = remove_inlined_functions


def remove_inlined_functions(node):
    try:
        node.remove_inlined_functions()
    except AttributeError as e:
        if not str(e).endswith("has no attribute 'remove_inlined_functions'"):
            raise RuntimeError(f"Raised AttributeError {e}")
