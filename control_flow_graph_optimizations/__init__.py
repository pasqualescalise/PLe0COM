#!/usr/bin/env python3

"""Control Flow Graph Optimizations: this optimizations operate on the CFG,
after all the CFG analysis"""

from control_flow_graph_optimizations.remove_inlined_functions import remove_inlined_functions
from control_flow_graph_optimizations.dead_variable_elimination import perform_dead_variable_elimination
from control_flow_graph_optimizations.chain_load_store_elimination import perform_chain_load_store_elimination
from control_flow_graph_analyses.liveness_analysis import perform_liveness_analysis, liveness_analysis_representation
from cfg import ControlFlowGraph
from logger import h3


def perform_control_flow_graph_optimizations(program, cfg, optimization_level):
    recomputed_liveness = False

    if optimization_level > 1:
        print(h3("REMOVE INLINED FUNCTIONS"))
        program.navigate(remove_inlined_functions, quiet=True)
        cfg = ControlFlowGraph(program)  # rebuild the ControlFlowGraph since BasicBlocks have disappeared
        perform_liveness_analysis(cfg)

        print(h3("DEAD VARIABLE ELIMINATION"))
        recomputed_liveness |= perform_dead_variable_elimination(cfg)

        print(h3("CHAIN LOAD STORE ELIMINATION"))
        recomputed_liveness |= perform_chain_load_store_elimination(cfg)

    if recomputed_liveness:
        print(h3("Recomputed liveness analysis"))
        print(liveness_analysis_representation(cfg))

    return cfg
