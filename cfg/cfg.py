#!/usr/bin/env python3

"""First transform the code into BasicBlocks, then create a
ControlFlowGraph of all the BasicBlocks that allows further
analyses and optimizations"""

from ir.ir import BranchInstruction, InstructionList, LabelInstruction
from ir.function_tree import FunctionTree
from logger import ii, di, remove_formatting, yellow, blue


class BasicBlock():
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

        # wheter or not this BasicBlock is the entry block of a function
        self.entry = False

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
            if self.instrs[-1].is_unconditional() and not self.instrs[-1].is_call():
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


class ControlFlowGraph(list):
    """Control Flow Graph representation"""

    def __init__(self, root):
        super().__init__()
        FunctionTree.navigate(create_basic_blocks, self, quiet=True)

        for bb in self:
            if bb.target:
                bb.target_bb = self.find_target_bb(bb.target)
            bb.remove_useless_next()

    # return a dictionary of {FunctionDef: entry Basic Block}
    def heads(self):
        bbs = {bb.get_function(): bb for bb in self if bb.entry}
        return bbs

    def tails(self):
        """Return a list of all the basic block that do not have successors"""
        tail = []
        for bb in self:
            if bb.next is None and bb.target is None:
                tail.append(bb)

        return tail

    def cfg_to_dot(self):
        """Get the CFG in graphviz dot"""
        dot = "digraph G {\n"
        for n in self:
            dot += n.graphviz_repr()

        heads = self.heads()
        for p in heads:
            bb = heads[p]
            dot += f"{p.symbol.name} [shape=box];\n"
            if len(bb.live_in):
                dot += f'{p.symbol.name} -> {id(bb)} [label="{bb.live_in}"];\n'
            else:
                dot += f'{p.symbol.name} -> {id(bb)} [label="{{}}"];\n'
        dot += "}\n"
        return remove_formatting(dot)

    def find_target_bb(self, label):
        """Return the BB that contains a given label;
        Support function for creating/exploring the CFG"""
        for bb in self:
            if label in bb.labels:
                return bb
        raise RuntimeError(f"Label {label} not found in any Basic Block")


def convert_instruction_list_to_bbs(self, basic_blocks):
    bbs = []
    # accumulator for instructions to be inserted in the next BasicBlock
    instructions = []
    # accumulator for the labels that refer to this BasicBlock
    labels = []

    for instruction in self.children:
        if isinstance(instruction, LabelInstruction):
            label = instruction.label
            if len(instructions) > 0:
                bb = BasicBlock(instrs=instructions, labels=labels)
                instructions = []

                if len(bbs) > 0:
                    bbs[-1].next = bb
                bbs.append(bb)

                labels = [label]
            else:
                # empty instruction, keep just the label
                labels.append(label)

        instructions.append(instruction)

        # if this BranchInstruction is not a function call, it marks the end of a BasicBlock
        if isinstance(instruction, BranchInstruction) and not instruction.is_call():
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

    # the first block is the function entry block
    bbs[0].entry = True

    basic_blocks += bbs


InstructionList.convert_to_basic_blocks = convert_instruction_list_to_bbs


# Create a list of BasicBlocks (the ControlFlowGraph) by grouping together
# instructions
#
# XXX: since this happens after the lowering, the only InstructionLists that
#      will be converted are function bodies
def create_basic_blocks(node, basic_blocks):
    try:
        node.convert_to_basic_blocks(basic_blocks)
    except AttributeError as e:
        if e.name != "convert_to_basic_blocks":
            raise RuntimeError(f"Raised AttributeError {e}")
