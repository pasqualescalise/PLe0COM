#!/usr/bin/env python3

"""Control Flow Graph Optimizations: this optimizations operate on the CFG,
after all the CFG analysis"""

from control_flow_graph_optimizations.remove_inlined_functions import remove_inlined_functions
from logger import h3


def perform_control_flow_graph_optimizations(program, cfg, optimization_level):
    if optimization_level > 1:
        print(h3("REMOVE INLINED FUNCTIONS"))
        program.navigate(remove_inlined_functions, quiet=True)
