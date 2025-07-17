#!/usr/bin/env python3

"""Post Lowering Optimizations: this optimizations operate on low-level IR nodes"""

from copy import deepcopy

from ir import BranchStat, StoreStat, ArrayType, PointerType, SaveSpaceStat, LoadStat, TYPENAMES, EmptyStat, new_temporary
from codegenhelp import REGISTER_SIZE
from logger import h3, red, green, blue, magenta


def perform_post_lowering_optimizations(program):
    print(h3("MEMORY-TO-REGISTER PROMOTION"))
    memory_to_register_promotion(program)

    print(h3("FUNCTION INLINING"))
    program.navigate(function_inlining, quiet=True)


# FUNCTION INLINING

MAX_INSTRUCTION_TO_INLINE = 16


# Replace all the temporaries in all the instructions with equivalent ones
def replace_temporaries(instructions):
    mapping = {}  # keep track of already remapped temporaries
    for instruction in instructions:
        instruction.replace_temporaries(mapping)

    return instructions


# Remove all the return instructions and if it's needed, add a branch to
# an exit label to simulate a return
def remove_returns(instructions, returns):
    exit_label = TYPENAMES['label']()
    exit_stat = EmptyStat(instructions[0].parent, symtab=instructions[0].symtab)
    exit_stat.set_label(exit_label)
    exit_stat.marked_for_removal = False
    no_exit_label = True  # decides whether or not to put the label at the end

    for i in range(len(instructions)):
        instruction = instructions[i]
        instruction.marked_for_removal = False

        if isinstance(instruction, BranchStat) and instruction.is_return():
            instruction.marked_for_removal = True

            if i < len(instructions) - 1:  # if this isn't the last istruction, add a jump to an exit label
                no_exit_label = False
                instructions[i] = BranchStat(target=exit_label, symtab=instruction.symtab)
                instructions[i].marked_for_removal = False

    if not no_exit_label:
        instructions.append(exit_stat)

    instructions = list(filter(lambda x: not x.marked_for_removal, instructions))
    return instructions


def remove_save_space_statements(instructions, number_of_parameters, number_of_returns):
    if number_of_parameters > 0 and isinstance(instructions[-(number_of_parameters + 1)], SaveSpaceStat):
        return instructions[:-(number_of_parameters + 1)] + instructions[-(number_of_parameters):]
    if number_of_returns > 0 and isinstance(instructions[-1], SaveSpaceStat):
        return instructions[:-1]
    return instructions


# Change all StoreStat destinations from variables to temporaries, returning
# the mapping of the variables to the temporaries
def change_stores(instructions, variables):
    destinations = {}
    for var in variables:
        destinations[var] = new_temporary(instructions[0].symtab, var.stype)

    for instruction in instructions:
        if isinstance(instruction, StoreStat) and instruction.dest in destinations:
            instruction.dest = destinations[instruction.dest]
            instruction.killhint = instruction.dest

    return instructions, destinations


# Change all LoadStat symbols from variables to temporaries using the provided mapping
def change_loads(instructions, destinations):
    for instruction in instructions:
        if isinstance(instruction, LoadStat) and instruction.symbol in destinations:
            instruction.symbol = destinations[instruction.symbol]

    return instructions


# If this call-BranchStat can be inlined, get all the instructions of the function,
# apply transformations to them (substituting returns with branches to exit, ...),
# get all the instructions before and after the call, apply transformations to them
# (change store of parameters to store in registers, ...), then put everything together
def inline(self):
    if not self.is_call:
        return

    target_function_name = self.target.name
    target_definition = self.get_function_definition(self.target)

    if len(target_definition.body.body.children) < MAX_INSTRUCTION_TO_INLINE:
        target_definition_copy = deepcopy(target_definition)

        if self.get_function() != 'main':
            target_definition_copy.symbol = self.get_function().symbol
        else:
            target_definition_copy.symbol = ""  # TODO: check if this creates problems

        # split the current function in before:body-of-the-function-to-inline:after
        index = self.parent.children.index(self)
        previous_instructions = self.parent.children[:index]
        function_instructions = target_definition_copy.body.body.children
        next_instructions = self.parent.children[index + 1:]

        function_instructions = replace_temporaries(function_instructions)
        function_instructions = remove_returns(function_instructions, target_definition_copy.returns)
        previous_instructions = remove_save_space_statements(previous_instructions, len(target_definition_copy.parameters), len(target_definition_copy.returns))

        # change parameters stores and loads into movs between registers
        previous_instructions, parameters_destinations = change_stores(previous_instructions, target_definition_copy.parameters)
        function_instructions = change_loads(function_instructions, parameters_destinations)

        # change returns stores and loads into movs between registers
        function_instructions, returns_destinations = change_stores(function_instructions, target_definition_copy.returns)
        next_instructions = change_loads(next_instructions, returns_destinations)

        # recompact everything
        self.parent.children = previous_instructions + function_instructions + next_instructions

        for child in self.parent.children:
            child.parent = self.parent

        # reference counting: if no one is calling the inlined function, it can be removed
        # TODO: this creates problems: if a function that does not pass the CFG optimizations is inlined, if
        #       we remove it it's never checked; so maybe remove only before codegen?
        target_definition.called_by_counter -= 1
        if target_definition.called_by_counter == 0:
            target_definition.parent.remove(target_definition)

        if self.get_function() == 'main':
            print(green(f"Inlining function {magenta(f'{target_function_name}')} {green('inside the')} {magenta('main')} {green('function')}\n"))
        else:
            print(green(f"Inlining function {magenta(f'{target_function_name}')} {green('inside function')} {magenta(f'{self.get_function().symbol.name}')}\n"))


BranchStat.inline = inline


def function_inlining(node):
    try:
        node.inline()
    except AttributeError as e:
        if not str(e).endswith("has no attribute 'inline'"):
            raise RuntimeError(f"Raised AttributeError {e}")


# MEMORY TO REGISTER PROMOTION

# Remove the symbol from the symbol table and convert it to a register
def promote_symbol(symbol, root):
    instructions = root.body.children

    root.symtab.remove(symbol)
    symbol.alloct = 'reg'

    for i in range(0, len(instructions)):
        if type(instructions[i]) is StoreStat and instructions[i].dest == symbol:
            instructions[i].killhint = symbol


# A variable can be promoted from being stored in memory to being stored in a register if
#   - the variable is not used in any nested procedure
#   - the variable address is needed for something (example -> ArrayType, PointerType)
#   - the symbol type is not the same size as the registers
def memory_to_register_promotion(root):
    to_promote = []

    for symbol in root.symtab:
        if symbol.alloct not in ['auto', 'global'] and symbol.stype.size > 0:
            continue

        print(f"{blue('SYMBOL:')} {symbol}")

        if isinstance(symbol.stype, ArrayType) or isinstance(symbol.stype, PointerType):
            print(red("Can't promote because the symbol address needs to be accessible\n"))
            continue

        if symbol.used_in_nested_procedure:
            print(red("Can't promote because the symbol is used in a nested procedure\n"))
            continue

        if symbol.stype.size != REGISTER_SIZE:
            print(red("Can't promote because the symbol is not the same size as the registers\n"))
            continue

        print(green("Promoted\n"))
        to_promote.append(symbol)

    for symbol in to_promote:
        promote_symbol(symbol, root)

    for function_definition in root.defs.children:
        memory_to_register_promotion(function_definition.body)
