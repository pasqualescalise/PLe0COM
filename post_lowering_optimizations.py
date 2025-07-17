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


def get_function_definition(self, target_function_name):
    parent_function = self.get_function()
    while parent_function != 'global':
        defs = parent_function.body.defs

        for definition in defs.children:
            if definition.symbol.name == target_function_name:
                return definition

        parent_function = parent_function.get_function()

    program = self.find_the_program()
    defs = program.defs

    for definition in defs.children:
        if definition.symbol.name == target_function_name:
            return definition

    raise RuntimeError(f"Can't find function definition of function {target_function_name}")


def replace_temporaries(instructions):
    mapping = {}  # keep track of already remapped temporaries
    for instruction in instructions:
        instruction.replace_temporaries(mapping)


# Remove all the return instructions and change the destination of
# the store instructions to a register instead of a return symbol
def remove_returns(instructions, returns):
    destinations = []  # temporaries to put the return values in
    for i in range(len(returns)):
        destinations.append(new_temporary(instructions[0].symtab, returns[i].stype))

    exit_label = TYPENAMES['label']()
    exit_stat = EmptyStat(instructions[0].parent, symtab=instructions[0].symtab)
    exit_stat.set_label(exit_label)
    exit_stat.marked_for_removal = False
    no_exit_label = True  # decides whether or not to put the label at the end

    for i in range(len(instructions)):
        instruction = instructions[i]

        try:
            if instruction.marked_for_removal:
                continue
        except AttributeError:
            instruction.marked_for_removal = False

        if isinstance(instruction, BranchStat) and instruction.is_return():
            instruction.marked_for_removal = True

            if len(returns) > 0:
                # go backwards and remove the stores
                for j in range(1, len(returns) + 1):
                    store_instruction = instructions[i - j]
                    if isinstance(store_instruction, StoreStat) and store_instruction.dest.alloct == 'return':
                        store_instruction.dest = list(reversed(destinations))[j - 1]

            if i < len(instructions) - 1:  # if this isn't the last istruction, add a jump to an exit label
                no_exit_label = False
                instructions[i] = BranchStat(target=exit_label, symtab=instruction.symtab)
                instructions[i].marked_for_removal = False

    if not no_exit_label:
        instructions.append(exit_stat)

    instructions = list(filter(lambda x: not x.marked_for_removal, instructions))
    return instructions, destinations


def remove_save_space_statements(instructions, number_of_returns):
    if number_of_returns > 0 and isinstance(instructions[-1], SaveSpaceStat):
        return instructions[:-1]
    return instructions


# Replace the symbols used to load return variables from actual return symbols
# to symbols where those values are stored
def change_return_assignments(instructions, number_of_returns, destinations):
    if number_of_returns == 0:
        return instructions

    for i in range(number_of_returns * 2):
        instruction = instructions[i]
        if isinstance(instruction, LoadStat) and instruction.symbol.alloct == 'return':
            instruction.symbol = destinations[i // 2]

    return instructions


def inline(self):
    if not self.is_call:
        return

    target_function_name = self.target.name
    target_definition = get_function_definition(self, target_function_name)

    if len(target_definition.body.body.children) < MAX_INSTRUCTION_TO_INLINE:
        target_definition_copy = deepcopy(target_definition)
        target_definition_copy.symbol = self.get_function().symbol

        function_instructions = target_definition_copy.body.body.children

        replace_temporaries(function_instructions)
        function_instructions, destinations = remove_returns(function_instructions, target_definition_copy.returns)

        index = self.parent.children.index(self)

        previous_instructions = self.parent.children[:index]
        previous_instructions = remove_save_space_statements(previous_instructions, len(target_definition_copy.returns))

        next_instructions = self.parent.children[index + 1:]
        next_instructions = change_return_assignments(next_instructions, len(target_definition_copy.returns), destinations)

        self.parent.children = previous_instructions + function_instructions + next_instructions

        for child in self.parent.children:
            child.parent = self.parent

        target_definition.called_by_counter -= 1
        if target_definition.called_by_counter == 0:
            target_definition.parent.remove(target_definition)

        if self.get_function() == 'global':
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
