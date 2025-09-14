#!/usr/bin/env python3

"""Post Lowering Optimizations: this optimizations operate on low-level IR nodes"""

from ir.function_tree import FunctionTree
from ir.post_lowering_optimizations.memory_to_register_promotion import memory_to_register_promotion
from ir.post_lowering_optimizations.function_inlining import function_inlining
from logger import h3


def perform_post_lowering_optimizations(program, optimization_level):
    if optimization_level > 0:
        print(h3("MEMORY-TO-REGISTER PROMOTION"))
        memory_to_register_promotion(program)

    if optimization_level > 1:
        print(h3("FUNCTION INLINING"))
        FunctionTree.navigate(function_inlining, quiet=True)
