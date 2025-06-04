#!/usr/bin/env python3

"""Optimizations"""

from ir import *
from math import log

LOOP_UNROLLING_FACTOR = 2

def loop_unrolling(node):
    """Navigation action: unrolling
    (only for ForStat nodes the unrolling is performed)"""

    if log(LOOP_UNROLLING_FACTOR, 2) != 1:
        raise RuntimeError("Loop Unrolling factor must be a multiple of 2")

    if LOOP_UNROLLING_FACTOR < 2:
        print("Skipping Loop Unrolling because the LOOP_UNROLLING_FACTOR is " + repr(LOOP_UNROLLING_FACTOR))
        return

    try:
        node.unroll(LOOP_UNROLLING_FACTOR)
    except AttributeError as e:
        pass # not a ForStat
