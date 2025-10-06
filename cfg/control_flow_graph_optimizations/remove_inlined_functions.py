#!/usr/bin/env python3

"""Using reference counting, removed useless inlined functions;
this is done after the CFG so that the original code is still checked"""

from ir.function_tree import FunctionTree
from ir.ir import DefinitionList
from logger import green, magenta


def remove_inlined_functions():
    remove_inlined_functions_from_node(FunctionTree.root)


def remove_inlined_functions_from_node(node):
    for child in node.children:
        remove_inlined_functions_from_node(child)

    remove_inlined_functions_from_definition(node.definition.body.defs)


def remove_inlined_functions_from_definition(definition_list):
    new_definitions = []
    removed = 0

    for definition in definition_list.children:
        if definition.called_by_counter < 1:
            for sub_definition in definition.body.defs.children:  # move the not inlined definitions upwards
                if sub_definition.called_by_counter > 0:
                    new_definitions += [sub_definition]

            # remove the function symbol from SymbolTables, it's just cleaner
            FunctionTree.remove_from_symtabs(definition.symbol)

            removed += 1
            print(f"{green('Removed inlined function')} {magenta(f'{definition.symbol.name}')}")
        else:
            new_definitions += [definition]

    if removed > 0:
        new_definition_list = DefinitionList(parent=definition_list.parent, children=new_definitions)
        definition_list.parent.defs = new_definition_list
