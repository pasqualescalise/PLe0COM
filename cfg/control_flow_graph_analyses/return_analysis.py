#!/usr/bin/env python3

"""Check each path of the ControlFlowGraph of functions that
return parameters actually end with a return statement"""

from ir.ir import BranchStat
from logger import green


def perform_return_analysis(cfg):
    for bb in cfg.tails():
        function_definition = bb.get_function()
        if function_definition.parent is None:
            continue  # the main does not return anything

        number_of_returns = len(function_definition.returns)
        if number_of_returns > 0:
            last_instruction = bb.instrs[-1]
            if isinstance(last_instruction, BranchStat) and last_instruction.target is None:
                pass
            else:
                raise RuntimeError(f"At least one path of the function '{function_definition.symbol.name}' doesn't end with a return, even if one is needed")

    print(green("All procedures that need to return parameters correctly return them\n"))
