#!/usr/bin/env python3

"""Compute variable liveness, which indicates the instruction range when
a certain variable is actually needed """

from functools import reduce

from cfg.cfg import BasicBlock
from logger import ii, di, yellow, blue, cyan


def perform_liveness_analysis(cfg):
    out = []
    for bb in cfg:
        out.append(bb.liveness_iteration())

    while sum(out):
        out = []
        for bb in cfg:
            out.append(bb.liveness_iteration())

    for bb in cfg:
        bb.compute_instr_level_liveness()


def liveness_analysis_representation(cfg):
    res = ""

    for bb in cfg:
        res += f"{bb}\n"

        res += yellow("Liveness Sets") + " {\n"
        res += ii(f"{blue('Gen set:')} {bb.gen},\n")
        res += ii(f"{blue('Kill set:')} {bb.kill},\n\n")
        res += ii(f"{blue('Live in set:')} {bb.live_in},\n")
        res += ii(f"{blue('Live out set:')} {bb.live_out}\n")
        res += "}\n\n"

        res += yellow("Instruction liveness") + " {\n"
        for i in bb.instrs:
            res += ii(f"{blue('Instruction:')} '{i}' " + "{\n")
            res += di(f"{cyan('Live in set:')} {i.live_in},\n")
            res += di(f"{cyan('Live out set:')} {i.live_out}\n")
            res += ii("}\n")
        res += "}\n\n---\n\n"

    return res


def liveness_iteration(self):
    """Compute live_in and live_out approximation
    Returns: True if a fixed point is reached, False otherwise"""
    lin = len(self.live_in)
    lout = len(self.live_out)

    if self.next or self.target_bb:
        self.live_out = reduce(lambda x, y: x.union(y), [s.live_in for s in self.succ()], set([]))
    else:  # Consider live out all the global vars
        func = self.get_function()
        if func.parent is not None:  # main
            self.live_out = set(func.get_global_symbols())

    self.live_in = self.gen.union(self.live_out - self.kill)
    return not (lin == len(self.live_in) and lout == len(self.live_out))


BasicBlock.liveness_iteration = liveness_iteration


def compute_instr_level_liveness(self):
    """Compute live_in and live_out for each instruction"""
    currently_alive = set([]).union(self.live_out)

    for i in reversed(self.instrs):
        i.live_out = set(currently_alive)
        try:
            currently_alive -= set(i.killed_variables())
        except AttributeError:
            pass

        currently_alive |= set(i.used_variables())
        i.live_in = set(currently_alive)

    if not currently_alive == self.live_in:
        raise RuntimeError('Instruction level liveness or block level liveness incorrect')


BasicBlock.compute_instr_level_liveness = compute_instr_level_liveness
