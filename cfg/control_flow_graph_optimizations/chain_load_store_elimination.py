#!/usr/bin/env python3

"""Sometimes because of other optimizations load-store chains are created,
where symbols are copied one into the other for no apparent reason. This
optimization eliminates these useless instruction, substituting the correct
symbols in all the subsequent instructions

For example:
    t2 <- t1
    t3 <- t2
    t4 <- t3
    t5 <- t4

Becomes:
    t5 <- t1
"""

from ir.ir import StoreInstruction, LoadInstruction
from logger import green


def perform_chain_load_store_elimination(bb, debug_info):
    keep_going = False
    mapping = {}

    for instruction in bb.instrs:
        if not isinstance(instruction, (StoreInstruction, LoadInstruction)):
            continue

        # do not delete chains involving pointers
        if not (instruction.dest.alloc_class == 'reg' and instruction.source.alloc_class == 'reg' and not instruction.dest.is_pointer() and not instruction.source.is_pointer()):
            continue

        # XXX: can we do this also for non temporaries?
        if isinstance(instruction, StoreInstruction):
            if not instruction.dest.is_temporary:
                continue

        if isinstance(instruction, LoadInstruction):
            if not instruction.source.is_temporary:
                continue

        if instruction.dest in bb.live_out:  # do not overwrite symbols used in next BasicBlocks
            continue

        mapping[instruction.dest] = instruction.source

        index = bb.instrs.index(instruction)

        for instr in bb.instrs[index + 1:]:
            instr.replace_temporaries(mapping, create_new=False)

        bb.remove(instruction)
        instruction.parent.remove(instruction)
        print(f"{green('Removed chained instruction')} {instruction}")
        debug_info['chain_load_store_elimination'] += [instruction]
        keep_going = True

    return keep_going
