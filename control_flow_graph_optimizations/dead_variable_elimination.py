#!/usr/bin/env python3

"""Using liveness analysis, remove useless variables; then recompute the
liveness analysis until no useless variables are found"""

from control_flow_graph_analyses.liveness_analysis import perform_liveness_analysis
from logger import green


def perform_dead_variable_elimination(cfg):
    recomputed_liveness = False
    keep_going = True

    while keep_going:
        keep_going = False
        for bb in cfg:
            for instruction in bb.instrs:
                live_out_set = instruction.live_out
                kill_set = set(instruction.killed_variables())

                # an instruction is useless if the variable it modifies ("kills")
                # is not used ("live") after it
                if kill_set != set() and kill_set.intersection(live_out_set) == set():
                    bb.remove(instruction)
                    instruction.parent.remove(instruction)
                    print(f"{green('Removed useless instruction')} {instruction}")
                    keep_going = True

        if keep_going:
            perform_liveness_analysis(cfg)
            recomputed_liveness = True

    return recomputed_liveness
