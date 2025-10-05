#!/usr/bin/env python3

"""Code generation methods for all low-level nodes in the IR.
Codegen functions return an array of ASMInstructions"""

from ir.ir import IRInstruction, Symbol, InstructionList, Block, BranchInstruction, DefinitionList, FunctionDef, BinaryInstruction, PrintInstruction, ReadInstruction, LabelInstruction, LoadPointerInstruction, PointerType, StoreInstruction, LoadInstruction, LoadImmInstruction, UnaryInstruction, DataSymbolTable, TYPENAMES
from backend.codegenhelp import ASMInstruction, get_register_string, save_regs, restore_regs, REGS_CALLEESAVE, REGS_CALLERSAVE, REG_SP, REG_FP, REG_LR, REG_SCRATCH, CALL_OFFSET, access_static_chain_pointer, load_static_chain_pointer
from backend.datalayout import LocalSymbolLayout
from logger import red, green, magenta, italic, remove_formatting


def symbol_codegen(self, regalloc):
    if self.allocinfo is None:
        return []
    if not isinstance(self.allocinfo, LocalSymbolLayout):
        return [ASMInstruction(".comm", args=[green(f'{self.allocinfo.symname}'), self.allocinfo.bsize])]
    else:
        if self.allocinfo.fpreloff > 0:
            return [ASMInstruction(".equ", args=[green(f'{self.allocinfo.symname}'), self.allocinfo.fpreloff])]
        else:
            return [ASMInstruction(".equ", args=[green(f'{self.allocinfo.symname}'), self.allocinfo.fpreloff - regalloc.spill_room()])]


Symbol.codegen = symbol_codegen


def irinstruction_codegen(self, regalloc):
    raise RuntimeError("Can't execute codegen of an abstract class")


IRInstruction.codegen = irinstruction_codegen


def instruction_list_codegen(self, regalloc):
    res = []

    if len(self.children) > 0:
        for child in self.children:
            try:
                res += child.codegen(regalloc)
            except RuntimeError as e:
                raise RuntimeError(f"Child {child.type_repr()}, {id(child)} did not generate any code; error: {e}")
    return res


InstructionList.codegen = instruction_list_codegen


def block_codegen(self, regalloc):
    res = [ASMInstruction("", comment="new function")]

    parameters = []

    if self.parent.parent is None:
        for sym in self.symtab:
            res += sym.codegen(regalloc)
    else:
        # only this functions variables
        for sym in [x for x in self.symtab if x.function_symbol == self.parent.symbol]:
            res += sym.codegen(regalloc)
        parameters = self.parent.parameters

    # prelude
    res += save_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
    res += [ASMInstruction('mov', args=[get_register_string(REG_FP), get_register_string(REG_SP)])]
    res += [ASMInstruction('push', args=[f"{{{get_register_string(REG_SCRATCH)}}}"])]  # push the static chain pointer
    stacksp = self.stackroom + regalloc.spill_room() - 4
    res += [ASMInstruction('sub', args=[get_register_string(REG_SP), get_register_string(REG_SP), f"#{italic(f'{stacksp}')}"])]

    # save the first 4 parameters, in reverse order, on the stack
    for i in range(len(parameters[:4]) - 1, -1, -1):
        res += [ASMInstruction('push', args=[f"{{{get_register_string(i)}}}"])]

    regalloc.enter_function_body(self)
    try:
        res += self.body.codegen(regalloc)
    except AttributeError as e:
        print(red("Can't execute codegen"))
        raise RuntimeError(e)

    last_instruction_of_block = self.body.children[-1]
    if isinstance(last_instruction_of_block, BranchInstruction) and last_instruction_of_block.target is None:
        # optmization: if the last instruction is a return this instructions are useless
        pass
    else:
        res += [ASMInstruction('mov', args=[get_register_string(REG_SP), get_register_string(REG_FP)])]
        res += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        if self.parent.parent is None:
            res += [ASMInstruction('mov', args=[get_register_string(0), f"#{italic('0')}"], comment="program ended successfully")]  # TODO: add a way to exit with not zero
        res += [ASMInstruction('bx', args=[get_register_string(REG_LR)])]

    # the place that the loads use to resolve labels (using `ldr rx, =address`)
    res += [ASMInstruction('.ltorg', comment="constant pool")]

    try:
        res += self.defs.codegen(regalloc)
    except AttributeError as e:
        print(red("Can't execute codegen"))
        raise RuntimeError(e)

    return res


Block.codegen = block_codegen


def definitionlist_codegen(self, regalloc):
    res = []
    for child in self.children:
        res += child.codegen(regalloc)

    return res


DefinitionList.codegen = definitionlist_codegen


def functiondef_codegen(self, regalloc):
    if self.parent is None:
        res = [ASMInstruction('.global', args=[magenta('main')], additional_newlines=1)]
        res += [ASMInstruction(magenta("main:"), indentation=0)]
    else:
        res = [ASMInstruction(magenta(f"\n{self.symbol.name}:"), indentation=0)]
    res += self.body.codegen(regalloc)
    return res


FunctionDef.codegen = functiondef_codegen


def binary_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.srca)
    res += regalloc.gen_spill_load_if_necessary(self.srcb)
    ra = regalloc.get_register_for_variable(self.srca)
    rb = regalloc.get_register_for_variable(self.srcb)
    rd = regalloc.get_register_for_variable(self.dest)

    param = f"{ra}, {rb}"

    # algebric operations
    if self.op == "plus":
        res += [ASMInstruction('add', args=[rd, param])]
    elif self.op == "minus":
        res += [ASMInstruction('sub', args=[rd, param])]
    elif self.op == "times":
        res += [ASMInstruction('mul', args=[rd, param])]
    elif self.op == "slash":
        # XXX: this should never happen, since there is no "div" instruction in armv6
        pass
    elif self.op == "shl":
        res += [ASMInstruction('lsl', args=[rd, param])]
    elif self.op == "shr":
        res += [ASMInstruction('lsr', args=[rd, param])]
    elif self.op == "mod":
        res += [ASMInstruction('add', args=[rd, param])]
        res += [ASMInstruction('sub', args=[get_register_string(REG_SCRATCH), rb, f"#{italic('1')}"])]
        res += [ASMInstruction('and', args=[rd, rd, get_register_string(REG_SCRATCH)])]

    # conditional operations
    elif self.op == "eql":
        res += [ASMInstruction('cmp', args=[param])]
        res += [ASMInstruction('moveq', args=[rd, f"#{italic('1')}"])]
        res += [ASMInstruction('movne', args=[rd, f"#{italic('0')}"])]
    elif self.op == "neq":
        res += [ASMInstruction('cmp', args=[param])]
        res += [ASMInstruction('moveq', args=[rd, f"#{italic('0')}"])]
        res += [ASMInstruction('movne', args=[rd, f"#{italic('1')}"])]
    elif self.op == "lss":
        res += [ASMInstruction('cmp', args=[param])]
        res += [ASMInstruction('movlt', args=[rd, f"#{italic('1')}"])]
        res += [ASMInstruction('movge', args=[rd, f"#{italic('0')}"])]
    elif self.op == "leq":
        res += [ASMInstruction('cmp', args=[param])]
        res += [ASMInstruction('movle', args=[rd, f"#{italic('1')}"])]
        res += [ASMInstruction('movgt', args=[rd, f"#{italic('0')}"])]
    elif self.op == "gtr":
        res += [ASMInstruction('cmp', args=[param])]
        res += [ASMInstruction('movgt', args=[rd, f"#{italic('1')}"])]
        res += [ASMInstruction('movle', args=[rd, f"#{italic('0')}"])]
    elif self.op == "geq":
        res += [ASMInstruction('cmp', args=[param])]
        res += [ASMInstruction('movge', args=[rd, f"#{italic('1')}"])]
        res += [ASMInstruction('movlt', args=[rd, f"#{italic('0')}"])]

    # logic operations
    elif self.op == "and":
        res += [ASMInstruction('and', args=[rd, param])]
    elif self.op == "or":
        res += [ASMInstruction('orr', args=[rd, param])]

    else:
        raise RuntimeError(f"Operation {self.op} unexpected")

    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


BinaryInstruction.codegen = binary_codegen


def unary_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rs = regalloc.get_register_for_variable(self.src)
    rd = regalloc.get_register_for_variable(self.dest)

    # algebric operations
    if self.op == 'plus':
        if rs != rd:
            res += [ASMInstruction('mov', args=[rd, rs])]
    elif self.op == 'minus':
        res += [ASMInstruction('mvn', args=[rd, rs])]
        res += [ASMInstruction('add', args=[rd, rd, f"#{italic('1')}"])]

    # conditional operations
    elif self.op == 'odd':
        res += [ASMInstruction('and', args=[rd, rs, f"#{italic('1')}"])]

    # logic operations
    elif self.op == 'not':
        res += [ASMInstruction('cmp', args=[rs, f"#{italic('0')}"])]
        res += [ASMInstruction('moveq', args=[rd, f"#{italic('1')}"])]
        res += [ASMInstruction('movne', args=[rd, f"#{italic('0')}"])]

    else:
        raise RuntimeError(f"Unexpected operation {self.op}")

    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


UnaryInstruction.codegen = unary_codegen


def print_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rp = regalloc.get_register_for_variable(self.src)

    res += save_regs(REGS_CALLERSAVE)
    res += [ASMInstruction('mov', args=[get_register_string(0), rp])]
    if self.newline:
        res += [ASMInstruction('mov', args=[get_register_string(1), f"#{italic(1)}"])]
    else:
        res += [ASMInstruction('mov', args=[get_register_string(1), f"#{italic(0)}"])]
    if self.print_type.is_string():
        res += [ASMInstruction('bl', args=[magenta('__pl0_print_string')])]
    elif self.print_type == TYPENAMES['boolean']:
        res += [ASMInstruction('bl', args=[magenta('__pl0_print_boolean')])]
    elif self.print_type == TYPENAMES['ubyte']:
        res += [ASMInstruction('bl', args=[magenta('__pl0_print_unsigned_byte')])]
    elif self.print_type == TYPENAMES['ushort']:
        res += [ASMInstruction('bl', args=[magenta('__pl0_print_unsigned_short')])]
    elif self.print_type == TYPENAMES['byte']:
        res += [ASMInstruction('bl', args=[magenta('__pl0_print_byte')])]
    elif self.print_type == TYPENAMES['short']:
        res += [ASMInstruction('bl', args=[magenta('__pl0_print_short')])]
    else:
        res += [ASMInstruction('bl', args=[magenta('__pl0_print_integer')])]
    res += restore_regs(REGS_CALLERSAVE)
    return res


PrintInstruction.codegen = print_codegen


def read_codegen(self, regalloc):  # TODO: this is not in use now
    rd = regalloc.get_register_for_variable(self.dest)

    # punch a hole in the saved registers if one of them is the destination
    # of this "instruction"
    saved_regs = list(REGS_CALLERSAVE)
    if regalloc.var_to_reg[self.dest] in saved_regs:
        saved_regs.remove(regalloc.var_to_reg[self.dest])

    res = save_regs(saved_regs)
    res += [ASMInstruction('bl', args=[magenta('__pl0_read')])]
    res += [ASMInstruction('mov', args=[rd, get_register_string(0)])]
    res += restore_regs(saved_regs)
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


ReadInstruction.codegen = read_codegen


# TODO: documentation on the ABI
def call_codegen(call, regalloc):
    res = []

    # add space on the stack for the return values
    if len(call.returns) > 0:
        res += [ASMInstruction('add', args=[get_register_string(REG_SP), get_register_string(REG_SP), f"#{italic(f'{len(call.returns) * -4}')}"])]

    res += save_regs(REGS_CALLERSAVE)

    num_stack_parameters = len(call.parameters[4:])

    # push on the stack all parameters after the first four
    for param_to_put_in_the_stack in call.parameters[4:]:
        res += regalloc.gen_spill_load_if_necessary(param_to_put_in_the_stack)
        res += [ASMInstruction('push', args=[f"{{{regalloc.get_register_for_variable(param_to_put_in_the_stack)}}}"])]

    # put the first 4 parameters in r0-r3
    for i in range(len(call.parameters[:4]) - 1, -1, -1):
        res += regalloc.gen_spill_load_if_necessary(call.parameters[i])
        reg = get_register_string(i)
        var = regalloc.get_register_for_variable(call.parameters[i])

        if remove_formatting(var) not in ['r0', 'r1', 'r2', 'r3']:
            res += [ASMInstruction('mov', args=[reg, var])]
        else:
            # XXX: weird hack to resolve data dependencies:
            #      we have to get this value from one of r0-r3,
            #      but we may have already modified it; to solve this,
            #      use the caller saved register we just pushed on the stack
            pos = ['r0', 'r1', 'r2', 'r3'].index(remove_formatting(var))
            res += [ASMInstruction('ldr', args=[reg, f"[{get_register_string(REG_SP)}, #{4 * (pos + num_stack_parameters)}]"])]

    res += load_static_chain_pointer(call)

    res += [ASMInstruction('bl', args=[magenta(call.target.name)])]

    # put the first 4 return values from r0-r3 on the stack
    for i in range(len(call.returns[:4]) - 1, -1, -1):
        pos = 4 * (i + 4 + num_stack_parameters)  # TODO documentation
        res += [ASMInstruction('str', args=[get_register_string(i), f"[{get_register_string(REG_SP)}, #{pos}]"])]

    # pop the parameters pushed previously
    for param_to_put_in_the_stack in list(reversed(call.parameters[4:])):
        res += [ASMInstruction('pop', args=[f"{{{regalloc.get_register_for_variable(param_to_put_in_the_stack)}}}"])]
        res += regalloc.gen_spill_store_if_necessary(param_to_put_in_the_stack)

    res += restore_regs(REGS_CALLERSAVE)

    # finally, get the return values from the stack in the correct registers
    for i in range(len(call.returns)):
        if call.returns[i] != '_':
            reg = regalloc.get_register_for_variable(call.returns[i])
            res += [ASMInstruction('pop', args=[f"{{{reg}}}"])]
            res += regalloc.gen_spill_store_if_necessary(call.returns[i])
        else:
            res += [ASMInstruction('add', args=[get_register_string(REG_SP), get_register_string(REG_SP), f"#{italic(f'{4}')}"])]

    return res


def branch_codegen(self, regalloc):
    res = []

    if self.target is not None and not self.is_call():
        # just a branch

        target_label = magenta(self.target.name)
        if self.cond is None:
            return [ASMInstruction('b', args=[target_label])]
        else:
            res += regalloc.gen_spill_load_if_necessary(self.cond)
            rcond = regalloc.get_register_for_variable(self.cond)

            res += [ASMInstruction('tst', args=[rcond, rcond])]
            op = "beq" if self.negcond else "bne"
            res += [ASMInstruction(op, args=[target_label])]
            return res

    elif self.is_return():
        # save on the caller stack all return values after the first four
        for i in range(len(self.returns[4:]) - 1, -1, -1):
            ret = self.returns[4:][i]
            res += regalloc.gen_spill_load_if_necessary(ret)
            pos = CALL_OFFSET + 4 * (4 + i + len(self.parameters[4:]))  # TODO: documentation
            res += [ASMInstruction('str', args=[regalloc.get_register_for_variable(ret), f"[{get_register_string(REG_FP)}, #{pos}]"])]

        # XXX: this is a hack: to avoid data dependencies, like `mov r0, r1; mov r1, r0`,
        #      push the 4 registers with the return value, then pop them in r0-r3
        for i in range(len(self.returns[:4])):
            ret = self.returns[i]
            res += regalloc.gen_spill_load_if_necessary(ret)
            res += [ASMInstruction('push', args=[f"{{{regalloc.get_register_for_variable(ret)}}}"])]

        for i in range(len(self.returns[:4]) - 1, -1, -1):
            res += [ASMInstruction('pop', args=[f"{{{get_register_string(i)}}}"])]

        res += [ASMInstruction('mov', args=[get_register_string(REG_SP), get_register_string(REG_FP)])]
        res += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        res += [ASMInstruction('bx', args=[get_register_string(REG_LR)])]
        return res

    # this branch is a call
    return call_codegen(self, regalloc)


BranchInstruction.codegen = branch_codegen


def label_codegen(self, regalloc):
    return [ASMInstruction(magenta(f"{self.label.name}:"), indentation=1)]


LabelInstruction.codegen = label_codegen


def loadpointer_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)
    res = []

    alloc_info = self.symbol.allocinfo
    if isinstance(alloc_info, LocalSymbolLayout):
        res = [ASMInstruction('add', args=[rd, get_register_string(REG_FP), f"#{green(f'{alloc_info.symname}')}"])]
    else:
        res = [ASMInstruction('ldr', args=[rd, f"={magenta(f'{alloc_info.symname}')}"])]
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


LoadPointerInstruction.codegen = loadpointer_codegen


def store_codegen(self, regalloc):
    res = []

    if self.dest.alloct == 'reg' and self.symbol.alloct == 'reg' and not self.dest.is_pointer():
        res += regalloc.gen_spill_load_if_necessary(self.symbol)
        res += [ASMInstruction('mov', args=[regalloc.get_register_for_variable(self.dest), regalloc.get_register_for_variable(self.symbol)])]
        res += regalloc.gen_spill_store_if_necessary(self.dest)
        return res

    elif self.dest.alloct == 'reg':
        res += regalloc.gen_spill_load_if_necessary(self.dest)
        dest = f"[{regalloc.get_register_for_variable(self.dest)}]"

    else:
        alloc_info = self.dest.allocinfo
        if isinstance(alloc_info, LocalSymbolLayout):
            static_link = access_static_chain_pointer(self, self.dest)
            if static_link:
                res += static_link
                # if the static link is necessary use the offset contained in the scratch register
                dest = f"[{get_register_string(REG_SCRATCH)}, #{green(f'{alloc_info.symname}')}]"
            else:
                dest = f"[{get_register_string(REG_FP)}, #{green(f'{alloc_info.symname}')}]"

        else:
            res = [ASMInstruction('ldr', args=[get_register_string(REG_SCRATCH), f"={green(f'{alloc_info.symname}')}"])]
            dest = f"[{get_register_string(REG_SCRATCH)}]"

    # XXX: not entirely sure about this
    if self.dest.is_array():
        desttype = PointerType(self.dest.type.basetype)
    elif self.dest.is_pointer():
        desttype = self.dest.type.pointstotype
    else:
        desttype = self.dest.type

    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]

    res += regalloc.gen_spill_load_if_necessary(self.symbol)
    rsrc = regalloc.get_register_for_variable(self.symbol)

    res += [ASMInstruction(f'str{typeid}', args=[rsrc, dest])]
    return res


StoreInstruction.codegen = store_codegen


def load_codegen(self, regalloc):
    res = []

    if self.dest.alloct == 'reg' and self.symbol.alloct == 'reg' and not self.symbol.is_pointer():
        res += regalloc.gen_spill_load_if_necessary(self.symbol)
        res += [ASMInstruction('mov', args=[regalloc.get_register_for_variable(self.dest), regalloc.get_register_for_variable(self.symbol)])]
        res += regalloc.gen_spill_store_if_necessary(self.dest)
        return res

    elif self.symbol.alloct == 'reg':
        res += regalloc.gen_spill_load_if_necessary(self.symbol)
        src = f"[{regalloc.get_register_for_variable(self.symbol)}]"

    else:
        alloc_info = self.symbol.allocinfo
        if isinstance(alloc_info, LocalSymbolLayout):
            static_link = access_static_chain_pointer(self, self.symbol)
            if static_link:
                res += static_link
                # if the static link is necessary use the offset contained in the scratch register
                src = f"[{get_register_string(REG_SCRATCH)}, #{green(f'{alloc_info.symname}')}]"
            else:
                src = f"[{get_register_string(REG_FP)}, #{green(f'{alloc_info.symname}')}]"

        else:
            res = [ASMInstruction('ldr', args=[get_register_string(REG_SCRATCH), f"={green(f'{alloc_info.symname}')}"])]
            src = f"[{get_register_string(REG_SCRATCH)}]"

    # XXX: not entirely sure about this
    if self.symbol.is_array():
        desttype = PointerType(self.symbol.type.basetype)
    elif self.symbol.is_pointer():
        desttype = self.symbol.type.pointstotype
    else:
        desttype = self.symbol.type

    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]
    if typeid != '' and 'unsigned' not in desttype.qualifiers:
        typeid = f"s{typeid}"

    rdst = regalloc.get_register_for_variable(self.dest)
    res += [ASMInstruction(f'ldr{typeid}', args=[rdst, src])]
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


LoadInstruction.codegen = load_codegen


def loadimm_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)
    res = []

    if self.val == "True":
        self.val = 1
    elif self.val == "False":
        self.val = 0

    if self.val >= -256 and self.val < 256:
        if self.val < 0:
            rv = -self.val - 1
            op = "mvn"
        else:
            rv = self.val
            op = "mov"

        res += [ASMInstruction(op, args=[rd, f"#{italic(f'{rv}')}"])]
    else:
        res += [ASMInstruction("ldr", args=[rd, f"=#{italic(f'{self.val}')}"])]

    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


LoadImmInstruction.codegen = loadimm_codegen


def generate_data_section():
    res = [ASMInstruction(".data")]
    for symbol in DataSymbolTable.get_data_symtab():
        if symbol.is_string() and symbol.value is not None:
            res += [ASMInstruction(f"{symbol.name}:", args=[f".asciz \"{symbol.value}\""])]
        else:
            raise NotImplementedError("Don't have implemented storing non-string values is .data section")

    return res


def generate_code(program, regalloc):
    res = generate_data_section()
    res += [ASMInstruction(".text")]
    res += [ASMInstruction(".arch armv6")]
    res += [ASMInstruction(".syntax unified")]
    return res + program.codegen(regalloc)
