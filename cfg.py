#!/usr/bin/env python3

"""First transform the code into BasicBlocks, then create a
ControlFlowGraph of all the BasicBlocks that allows further
analyses and optimizations"""

from ir import BranchStat, StatList, FunctionDef
from logger import ii, di, remove_formatting, yellow, blue
from support import get_node_list


class BasicBlock(object):
    def __init__(self, next=None, instrs=None, labels=None):
        """Structure:
        Zero, one (next) or two (next, target_bb) successors
        Keeps information on labels (list of labels that refer to this BB)
        """
        self.next = next

        if instrs:
            self.instrs = instrs
        else:
            self.instrs = []

        try:
            if self.instrs[-1].is_call():
                self.target = None
            else:
                self.target = self.instrs[-1].target
        except AttributeError:
            self.target = None  # last instruction is not a branch

        if labels:
            self.labels = labels
        else:
            self.labels = []

        self.target_bb = None

        # liveness in respect to the whole cfg
        self.live_in = set([])
        self.live_out = set([])

        # compute kill and gen set for this block, as if it was a black box
        self.kill = set([])  # assigned
        self.gen = set([])  # use before assign

        for i in instrs:
            uses = set(i.used_variables())
            try:
                kills = set(i.killed_variables())
            except AttributeError:
                kills = set()

            uses.difference_update(self.kill)

            self.gen.update(uses)
            self.kill |= kills

        # total number of registers needed
        self.total_vars_used = len(self.gen.union(self.kill))

    def __repr__(self):
        res = f"{yellow('Basic Block')} {id(self)} " + "{\n"
        if self.next:
            res += ii(f"{blue('Next:')} {id(self.next)},\n")
        else:
            res += ii(f"{blue('Next:')} {self.next},\n")
        res += ii(f"{blue('Target:')} {self.target},\n")
        res += ii(f"{blue('Instructions:')}\n")
        for i in self.instrs:
            res += di(f"{i}\n")

        res += "}\n"

        return res

    def graphviz_repr(self):
        """Print in graphviz dot format"""
        instrs = f"{self.labels}" + '\\n' if len(self.labels) else ''
        instrs += '\\n'.join([repr(i) for i in self.instrs])
        res = f'{id(self)} [label="BB {id(self)}' + '\\n' + f'{instrs}"];\n'
        if self.next:
            if len(self.next.live_in) > 0:
                res += f'{id(self)} -> {id(self.next)} [label="{self.next.live_in}"];\n'
            else:
                res += f'{id(self)} -> {id(self.next)} [label="{{}}"];\n'
        if self.target_bb:
            if len(self.target_bb.live_in) > 0:
                res += f'{id(self)} -> {id(self.target_bb)} [style=dashed,label="{self.target_bb.live_in}"];\n'
            else:
                res += f'{id(self)} -> {id(self.target_bb)} [style=dashed,label="{{}}"];\n'
        if not (self.next or self.target_bb):
            if len(self.live_out) > 0:
                res += f'{id(self)} -> exit{id(self.get_function())} [label="{self.live_out}"];\n'
            else:
                res += f'{id(self)} -> exit{id(self.get_function())} [label="{{}}"];\n'
        return res

    def succ(self):
        return [s for s in [self.target_bb, self.next] if s]

    def remove_useless_next(self):
        """Check if unconditional branch, in that case remove next"""
        try:
            if self.instrs[-1].is_unconditional():
                self.next = None
        except AttributeError:
            pass

    def get_function(self):
        return self.instrs[0].get_function()

    def remove(self, instruction):
        try:
            self.instrs.remove(instruction)
        except ValueError:
            raise RuntimeError(f"Can't find instruction '{instruction}' to remove in BasicBlock {id(self)}")


def stat_list_to_bb(stat_list):
    bbs = []
    # accumulator for statements to be inserted in the next BasicBlock
    instructions = []
    # accumulator for the labels that refer to this BasicBlock
    labels = []

    for statement in stat_list.children:
        try:
            label = statement.get_label()
            if label:
                if len(instructions) > 0:
                    bb = BasicBlock(instrs=instructions, labels=labels)
                    instructions = []

                    if len(bbs) > 0:
                        bbs[-1].next = bb
                    bbs.append(bb)

                    labels = [label]
                else:
                    # empty statement, keep just the label
                    labels.append(label)
        except Exception:
            pass  # instruction doesn't have a label

        instructions.append(statement)

        # if this is BranchStat is a function call, it marks the end of a BasicBlock
        if isinstance(statement, BranchStat) and not statement.is_call():
            bb = BasicBlock(instrs=instructions, labels=labels)
            instructions = []

            if len(bbs):
                bbs[-1].next = bb
            bbs.append(bb)

            labels = []

    if len(instructions) > 0 or len(labels) > 0:
        bb = BasicBlock(instrs=instructions, labels=labels)

        if len(bbs):
            bbs[-1].next = bb
        bbs.append(bb)

    return bbs


class ControlFlowGraph(list):
    """Control Flow Graph representation"""

    def __init__(self, root):
        super().__init__()
        stat_lists = [n for n in get_node_list(root, quiet=True) if isinstance(n, StatList)]
        self += sum([stat_list_to_bb(sl) for sl in stat_lists], [])  # XXX: I really don't like this syntax

        for bb in self:
            if bb.target:
                bb.target_bb = self.find_target_bb(bb.target)
            bb.remove_useless_next()

    def heads(self):
        """Get a dictionary of BasicBlocks that are only reached via function
        call or global entry point"""
        defs = []
        for bb1 in self:
            head = True
            for bb2 in self:
                if bb2.next == bb1 or bb2.target_bb == bb1:
                    head = False
                    break
            if head:
                defs.append(bb1)

        res = {}
        for bb in defs:
            first = bb.instrs[0]
            parent = first.parent
            while parent and not isinstance(parent, FunctionDef):
                parent = parent.parent

            if not parent:
                res['main'] = bb
            else:
                res[parent] = bb
        return res

    def tails(self):
        """Return a list of all the basic block that do not have successors"""
        tail = []
        for bb in self:
            if bb.next is None and bb.target is None:
                tail.append(bb)

        return tail

    def print_cfg_to_dot(self, filename):
        """Print the CFG in graphviz dot to file"""
        f = open(filename, "w")
        dot = "digraph G {\n"
        for n in self:
            dot += n.graphviz_repr()

        heads = self.heads()
        for p in heads:
            bb = heads[p]
            if p == 'main':
                dot += 'main [shape=box];\n'
                if len(bb.live_in):
                    dot += f'main -> {id(bb)} [label="{bb.live_in}"];\n'
                else:
                    dot += f'main -> {id(bb)} [label="{{}}"];\n'
            else:
                dot += f"{p.symbol.name} [shape=box];\n"
                if len(bb.live_in):
                    dot += f'{p.symbol.name} -> {id(bb)} [label="{bb.live_in}"];\n'
                else:
                    dot += f'{p.symbol.name} -> {id(bb)} [label="{{}}"];\n'
        dot += "}\n"
        f.write(remove_formatting(dot))
        f.close()

    def find_target_bb(self, label):
        """Return the BB that contains a given label;
        Support function for creating/exploring the CFG"""
        for bb in self:
            if label in bb.labels:
                return bb
        raise RuntimeError(f"Label {label} not found in any Basic Block")
