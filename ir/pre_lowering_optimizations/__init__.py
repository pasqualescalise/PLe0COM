#!/usr/bin/env python3

"""Pre Lowering Optimizations: this optimizations operate on high-level IR nodes"""

from ir.pre_lowering_optimizations.node_expansion import perform_node_expansion
from ir.pre_lowering_optimizations.loop_unrolling import perform_loop_unrolling
from logger import h3


def perform_pre_lowering_optimizations(program, optimization_level):
    print(h3("NODE EXPANSION"))
    perform_node_expansion(program)

    if optimization_level > 1:
        print(h3("LOOP UNROLLING"))
        perform_loop_unrolling(program)
