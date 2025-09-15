#!/usr/bin/env python3

"""Abstract Syntax Tree Optimizations: this optimizations operate after the parser
on the nodes of the AST"""

from frontend.abstract_syntax_tree_optimizations.node_expansion import perform_node_expansion
from frontend.abstract_syntax_tree_optimizations.loop_unrolling import perform_loop_unrolling
from logger import h3


def perform_abstract_syntax_tree_optimizations(program, optimization_level):
    print(h3("NODE EXPANSION"))
    perform_node_expansion(program)

    if optimization_level > 1:
        print(h3("LOOP UNROLLING"))
        perform_loop_unrolling(program)
