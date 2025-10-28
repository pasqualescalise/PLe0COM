#!/usr/bin/env python3

"""Register allocation pass, using the linear-scan algorithm.
Assumes that all temporaries can be allocated to any register (because of this,
it does not work with non integer types)."""

from logger import green, yellow, cyan, bold

# the register of all spilled temporaries is set to SPILL_FLAG
SPILL_FLAG = 999


def remove_non_regs(set):
    return {var for var in set if var.alloc_class == 'reg'}


class RegisterAllocation(object):
    """Object that contains the information about where each temporary is
    allocated.

    Spill handling is done by reserving 2 machine registers to be filled
    as late as possible, and spilled again as soon as possible. This class is
    responsible for filling these registers."""

    def __init__(self, var_to_reg, num_spill, nregs):
        self.var_to_reg = var_to_reg
        self.num_spill = num_spill
        self.nregs = nregs
        self.vartospillframeoffset = dict()
        self.spillregi = 0
        self.spillframeoffseti = 0

    def update(self, otherra):
        self.var_to_reg.update(otherra.var_to_reg)
        self.num_spill += otherra.num_spill

    def spill_room(self):
        return self.num_spill * 4

    def dematerialize_spilled_var_if_necessary(self, var):
        """Resets the register used for a spill variable when we know that instance
        of the variable is now dead."""
        if self.var_to_reg[var] >= self.nregs - 2:
            self.var_to_reg[var] = SPILL_FLAG

    def materialize_spilled_var_if_necessary(self, var):
        """Decide which of the spill-reserved registers to fill with a spilled
        variable. Also, decides to which stack location the variable is spilled
        to, the first time this method is called for that variable.

        Returns True iff the variable was spilled in the register
        allocation phase.

        The algorithm used to decide which register is filled is simple: the
        register chosen is the one that was not chosen the last time. It always
        works and it never needs any information about which registers are live
        at a given time."""

        if self.var_to_reg[var] != SPILL_FLAG:
            # already allocated and filled! nothing to do
            if self.var_to_reg[var] >= self.nregs - 2:
                return True
            return False

        # decide the register
        self.var_to_reg[var] = self.spillregi + self.nregs - 2
        self.spillregi = (self.spillregi + 1) % 2

        # decide the location in the current frame
        if not (var in self.vartospillframeoffset):
            self.vartospillframeoffset[var] = self.spillframeoffseti
            self.spillframeoffseti += 4
        return True

    def __repr__(self):
        variables_name_len = list(map(len, map(str, self.var_to_reg.keys())))
        max_len = max(variables_name_len)
        indentation = list(map(lambda x: max_len - x, variables_name_len))

        res = yellow("Register Allocation for variables")
        res += " [\n"

        i = 0
        for var in self.var_to_reg:
            if self.var_to_reg[var] == 999:
                res += f"\t{var}: {' ' * indentation[i]}{yellow('SPILLED REGISTER')}\n"
            else:
                res += f"\t{var}: {' ' * indentation[i]}{' ' * self.var_to_reg[var] * 2}{cyan(f'{self.var_to_reg[var]}')}\n"
            i += 1

        res += "]\n"

        return res


class LinearScanRegisterAllocator(object):
    """The register allocator. Produces RegisterAllocation objects from a control
    flow graph."""

    def __init__(self, cfg, nregs):
        self.cfg = cfg
        self.nregs = nregs

        # liveness of a variable on entry to each instruction
        # in order of start point
        self.var_liveness = []  # {var=var, liveness=[indexes]}
        # list of all variables
        self.all_variables = []
        self.var_to_reg = {}

    def compute_liveness_intervals(self):
        """Computes liveness intervals for the whole program. Note that the CFG
        is flattened: this is the reason why the linear scan register allocation
        algorithm does not handle liveness holes properly"""
        inst_index = 0
        min_gen = {}
        max_use = {}
        vars = set()

        # get the index of the instruction when a variable is generated and when it is killed
        for bb in self.cfg:
            for instr in bb.instrs:
                live_out = remove_non_regs(instr.live_out)
                live_in = remove_non_regs(instr.live_in)

                for out_var in live_out:
                    if out_var not in min_gen:
                        min_gen[out_var] = inst_index
                        max_use[out_var] = inst_index

                for in_var in live_in:
                    max_use[in_var] = inst_index

                vars |= live_out | live_in

                inst_index += 1

        for var in vars:
            gen = min_gen[var]
            kill = max_use[var]
            self.var_liveness.insert(0, {"var": var, "interval": range(gen, kill)})

        try:
            self.var_liveness.sort(key=lambda x: x['interval'][0])
        except IndexError:
            # XXX: better error message, this is an important compilation error to tell the user
            for i in self.var_liveness:
                if i['interval'].start == i['interval'].stop:
                    raise RuntimeError(f"Variable {i['var'].name} is only used at instruction {i['interval'].start}; it may be useless or there may be another mistake earlier during compilation")

        self.all_variables = list(vars)

    def __call__(self):
        """Linear-scan register allocation (a variant of the more general
                graph coloring algorithm known as "left-edge")"""

        self.compute_liveness_intervals()

        live = []
        free_regs = set(range(0, self.nregs - 2))  # -2 for spill room
        num_spill = 0

        for live_interval in self.var_liveness:
            start = live_interval["interval"][0]

            # expire old intervals
            i = 0
            while i < len(live):
                not_live_candidate = live[i]
                if not_live_candidate["interval"][-1] < start:
                    live.pop(i)
                    free_regs.add(self.var_to_reg[not_live_candidate["var"]])
                i += 1

            if len(free_regs) == 0:
                to_spill = live[-1]
                # keep the longest interval
                if to_spill["interval"][-1] > live_interval["interval"][-1]:
                    # actually spill
                    self.var_to_reg[live_interval["var"]] = self.var_to_reg[to_spill["var"]]
                    self.var_to_reg[to_spill["var"]] = SPILL_FLAG
                    live.pop(-1)  # remove spill from active
                    live.append(live_interval)  # add i to active
                else:
                    self.var_to_reg[live_interval["var"]] = SPILL_FLAG
                num_spill += 1

            else:
                self.var_to_reg[live_interval["var"]] = free_regs.pop()
                live.append(live_interval)

            # sort the active intervals by increasing end point
            live.sort(key=lambda li: li['interval'][-1])

        return RegisterAllocation(self.var_to_reg, num_spill, self.nregs)

    def get_liveness_intervals(self):
        res = yellow("Liveness intervals")
        res += " [\n"

        variables_name_len = list(map(len, map(str, map(lambda v: v['var'], self.var_liveness))))
        max_len = max(variables_name_len)
        indentation = list(map(lambda x: max_len - x, variables_name_len))

        i = 0
        for interval in self.var_liveness:
            var = interval['var']
            start = interval['interval'].start
            stop = interval['interval'].stop

            res += f"{' ' * 4}Variable {green(f'{var}')} is {bold('live')} in the instruction interval {' ' * indentation[i]}{cyan(f'({start} - {stop})')},\n"
            i += 1

        res += "]\n"

        return res
