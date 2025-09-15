#!/usr/bin/env python3

"""It's faster to directly execute function code instead of jumping to one:
when possible, directly replace the function call with its code"""

from copy import deepcopy

from ir.function_tree import FunctionTree
from ir.ir import BranchInstruction, StoreInstruction, LoadInstruction, EmptyInstruction, TYPENAMES
from logger import green, magenta


MAX_INSTRUCTION_TO_INLINE = 16


# Replace all the temporaries in all the instructions with equivalent ones
def replace_temporaries(instructions):
    mapping = {}  # keep track of already remapped temporaries
    for instruction in instructions:
        instruction.replace_temporaries(mapping, create_new=True)

    return instructions


# Remove all the return instructions and if it's needed, add a branch to
# an exit label to simulate a return
def remove_returns(instructions, returns):
    exit_label = TYPENAMES['label']()
    exit_instr = EmptyInstruction(instructions[0].parent, symtab=instructions[0].symtab)
    exit_instr.set_label(exit_label)
    exit_instr.marked_for_removal = False
    no_exit_label = True  # decides whether or not to put the label at the end

    for i in range(len(instructions)):
        instruction = instructions[i]
        instruction.marked_for_removal = False

        if isinstance(instruction, BranchInstruction) and instruction.is_return():
            instruction.marked_for_removal = True

            if i < len(instructions) - 1:  # if this isn't the last istruction, add a jump to an exit label
                no_exit_label = False
                instructions[i] = BranchInstruction(target=exit_label, symtab=instruction.symtab)
                instructions[i].marked_for_removal = False

    if not no_exit_label:
        instructions.append(exit_instr)

    instructions = list(filter(lambda x: not x.marked_for_removal, instructions))
    return instructions


# Whenever there's a return, add before the StoreInstructions that put the value
# returned by the inlined function into the symbol used by the inliner function
def add_returns_stores(instructions, returns):
    stores_indices = []

    for i in range(len(instructions)):
        instruction = instructions[i]
        instruction.marked_for_removal = False

        if isinstance(instruction, BranchInstruction) and instruction.is_return():
            new_stores = []
            for j in range(len(returns)):
                if returns[j] != "_":  # skip dontcares
                    new_store = StoreInstruction(parent=instruction.parent, dest=returns[j], symbol=instruction.returns[j], killhint=returns[j], symtab=instruction.symtab)
                    new_stores.append(new_store)
            stores_indices.append((i, new_stores))

    for stores_index in reversed(stores_indices):  # reversed order otherwise the indices get mixed
        i = stores_index[0]  # index in the instruction list
        for store in stores_index[1]:
            instructions.insert(i, store)
            i += 1

    return instructions


# Map the symbols used in the functions with the ones used in the call
# and return a dictionary mapping the two
def map_symbols(function_symbols, call_symbols):
    destinations = {}
    for i in range(len(function_symbols)):
        destinations[function_symbols[i]] = call_symbols[i]

    return destinations


# Change all LoadInstruction symbols from variables to temporaries using the provided mapping
def change_loads(instructions, destinations):
    for instruction in instructions:
        if isinstance(instruction, LoadInstruction) and instruction.symbol in destinations:
            if instruction.symbol.is_array() and destinations[instruction.symbol].is_pointer():
                # fix pass-by-reference, instead this becomes a move of the array address
                destinations[instruction.symbol].stype = instruction.symbol.stype
            instruction.symbol = destinations[instruction.symbol]

    return instructions


# If this call-BranchInstruction can be inlined, get all the instructions of the function,
# apply transformations to them (substituting returns with branches to exit, ...),
# get all the instructions before and after the call, apply transformations to them
# (change store of parameters to store in registers, ...), then put everything together
def inline(self):
    if not self.is_call():
        return

    target_definition = FunctionTree.get_function_definition(self.target)
    if len(target_definition.body.body.children) >= MAX_INSTRUCTION_TO_INLINE:
        return

    # avoid inlining recursive functions
    if self.target == self.get_function().symbol:
        return

    target_definition_copy = deepcopy(target_definition)
    target_definition_copy.symbol = self.get_function().symbol

    # split the current function in before:body-of-the-function-to-inline:after
    index = self.parent.children.index(self)
    previous_instructions = self.parent.children[:index]
    function_instructions = target_definition_copy.body.body.children
    next_instructions = self.parent.children[index + 1:]

    function_instructions = replace_temporaries(function_instructions)

    # change parameters stores and loads into movs between registers
    parameters_destinations = map_symbols(target_definition_copy.parameters, self.parameters)
    function_instructions = change_loads(function_instructions, parameters_destinations)

    # add instructions to store return variables in the correct registers
    function_instructions = add_returns_stores(function_instructions, self.returns)
    function_instructions = remove_returns(function_instructions, target_definition_copy.returns)

    # recompact everything
    self.parent.children = previous_instructions + function_instructions + next_instructions

    for local_symbol in target_definition.body.local_symtab:
        if local_symbol not in self.parent.parent.local_symtab:
            self.parent.parent.local_symtab.append(local_symbol)

    for child in self.parent.children:
        child.parent = self.parent

    # reference counting: if no one is calling the inlined function, it can be removed
    target_definition.called_by_counter -= 1

    print(green(f"Inlining function {magenta(f'{self.target.name}')} {green('inside function')} {magenta(f'{self.get_function().symbol.name}')}\n"))


BranchInstruction.inline = inline


def function_inlining(node):
    try:
        node.inline()
    except AttributeError as e:
        if e.name != "inline":
            raise RuntimeError(f"Raised AttributeError {e}")
