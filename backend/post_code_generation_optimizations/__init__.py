#!/usr/bin/env python3

"""Post Code Generation Optimizations: this optimizations operate on the source
code, as a string"""

from backend.post_code_generation_optimizations.add_literal_pools import add_literal_pools
from logger import h3


def perform_post_code_generation_optimizations(code, optimization_level):
    print(h3("ADD LITERAL POOLS"))
    code = add_literal_pools(code)

    return code
