#!/usr/bin/env python3

"""Control Flow Graph Optimizations: this optimizations operate on the CFG,
after all the CFG analysis. If instructions are changed or removed, the CFG
is updated and the liveness analysis is done again"""

from ir.function_tree import FunctionTree
from cfg.control_flow_graph_optimizations.remove_inlined_functions import remove_inlined_functions
from cfg.control_flow_graph_optimizations.dead_variable_elimination import perform_dead_variable_elimination
from cfg.control_flow_graph_optimizations.chain_load_store_elimination import perform_chain_load_store_elimination
from cfg.control_flow_graph_analyses.liveness_analysis import perform_liveness_analysis, liveness_analysis_representation
from cfg.cfg import ControlFlowGraph
from logger import h3, cyan


def perform_control_flow_graph_optimizations(program, cfg, optimization_level):
    recomputed_liveness = False

    if optimization_level > 1:
        print(h3("REMOVE INLINED FUNCTIONS"))
        remove_inlined_functions()

        # rebuild the FunctionTree and the ControlFlowGraph
        FunctionTree.populate_function_tree(program, FunctionTree.root.symbol)
        cfg = ControlFlowGraph(program)
        perform_liveness_analysis(cfg)

        print(h3("DEAD VARIABLE ELIMINATION"))
        recomputed_liveness |= apply_cfg_optimization(cfg, perform_dead_variable_elimination)

        print(h3("CHAIN LOAD STORE ELIMINATION"))
        recomputed_liveness |= apply_cfg_optimization(cfg, perform_chain_load_store_elimination)

    if len(cfg) == 0:
        raise RuntimeError("The ControlFlowGraph is empty, either there's a problem or a useless program is being compiled")

    if recomputed_liveness:
        print(h3("Recomputed liveness analysis"))
        print(liveness_analysis_representation(cfg))

    return cfg


# Apply the optimization on the ControlFlowGraph until no changes are made anymore
def apply_cfg_optimization(cfg, optimization_pass):
    recomputed_liveness = False
    keep_going = True

    while keep_going:
        keep_going = False
        for bb in cfg:
            keep_going |= optimization_pass(bb)

        if keep_going:
            update_cfg(cfg)
            recomputed_liveness = True

    return recomputed_liveness


# After optimizations, eliminate useless BasicBlocks and recompute liveness analysis
# TODO: what happens if we remove a whole function that was not inlined?
def update_cfg(cfg):
    for bb in reversed(cfg):
        if len(bb.instrs) == 0:
            print(cyan("Removed a BasicBlock"))
            cfg.remove(bb)

    perform_liveness_analysis(cfg)
