#!/usr/bin/env python3

"""Code generation methods for all low-level nodes in the IR.
Codegen functions return a string, consisting of the assembly code they
correspond to"""

from ir.ir import IRInstruction, Symbol, Block, BranchStat, DefinitionList, FunctionDef, BinStat, PrintStat, ReadStat, EmptyStat, LoadPtrToSym, PointerType, StoreStat, LoadStat, LoadImmStat, UnaryStat, DataSymbolTable, TYPENAMES
from backend.codegenhelp import comment, get_register_string, save_regs, restore_regs, REGS_CALLEESAVE, REGS_CALLERSAVE, REG_SP, REG_FP, REG_LR, REG_SCRATCH, CALL_OFFSET, access_static_chain_pointer, load_static_chain_pointer
from backend.datalayout import LocalSymbolLayout
from logger import ii, hi, red, green, yellow, blue, magenta, cyan, italic, remove_formatting


def symbol_codegen(self, regalloc):
    if self.allocinfo is None:
        return ""
    if not isinstance(self.allocinfo, LocalSymbolLayout):
        return ii(f".comm {green(f'{self.allocinfo.symname}')}, {self.allocinfo.bsize}\n")
    else:
        if self.allocinfo.fpreloff > 0:
            return ii(f".equ {green(f'{self.allocinfo.symname}')}, {self.allocinfo.fpreloff}\n")
        else:
            return ii(f".equ {green(f'{self.allocinfo.symname}')}, {self.allocinfo.fpreloff - regalloc.spill_room()}\n")


Symbol.codegen = symbol_codegen


def irinstruction_codegen(self, regalloc):
    res = ii(f"{comment(f'IRInstruction {self.type()}, {id(self)}')}")  # TODO: remove this stuff
    if "children" in dir(self) and len(self.children):
        for node in self.children:
            try:
                try:
                    label = node.get_label()
                    res += hi(magenta(f"{label.name}:\n"))
                except Exception:
                    pass
                res += node.codegen(regalloc)
            except RuntimeError as e:
                raise RuntimeError(f"Node {node.type()}, {id(node)} did not generate any code; error: {e}")
    return res


IRInstruction.codegen = irinstruction_codegen


def block_codegen(self, regalloc):
    res = ii(f"{comment('block')}")

    parameters = []

    if self.parent is None:
        for sym in self.symtab:
            res += sym.codegen(regalloc)
    else:
        # only this functions variables
        for sym in [x for x in self.symtab if x.function_symbol == self.parent.symbol]:
            res += sym.codegen(regalloc)
        parameters = self.parent.parameters

    if self.parent is None:
        res += ii(f".global {magenta('__pl0_start')}\n\n")
        res += magenta("__pl0_start:\n")

    # prelude
    res += save_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
    res += ii(f"{blue('mov')} {get_register_string(REG_FP)}, {get_register_string(REG_SP)}\n")
    res += ii(f"{cyan('push')} {{{get_register_string(REG_SCRATCH)}}}\n")  # push the static chain pointer
    stacksp = self.stackroom + regalloc.spill_room() - 4
    res += ii(f"{yellow('sub')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{stacksp}')}\n")

    # save the first 4 parameters, in reverse order, on the stack
    for i in range(len(parameters[:4]) - 1, -1, -1):
        res += ii(f"{cyan('push')} {{{get_register_string(i)}}}\n")

    regalloc.enter_function_body(self)
    try:
        res += self.body.codegen(regalloc)
    except AttributeError as e:
        print(red("Can't execute codegen"))
        raise RuntimeError(e)

    last_statement_of_block = self.body.children[-1]
    if isinstance(last_statement_of_block, BranchStat) and last_statement_of_block.target is None:
        # optmization: if the last statement is a return this instructions are useless
        pass
    else:
        res += ii(f"{blue('mov')} {get_register_string(REG_SP)}, {get_register_string(REG_FP)}\n")
        res += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        res += ii(f"{red('bx')} {get_register_string(REG_LR)}\n")

    # the place that the loads use to resolve labels (using `ldr rx, =address`)
    # TODO: this still breaks if a function has more than 510 instructions
    res += ii(".ltorg")
    res += ii(f"{comment('constant pool')}")

    try:
        res += self.defs.codegen(regalloc)
    except AttributeError as e:
        print(red("Can't execute codegen"))
        raise RuntimeError(e)

    return res


Block.codegen = block_codegen


def deflist_codegen(self, regalloc):
    return ''.join([child.codegen(regalloc) for child in self.children])


DefinitionList.codegen = deflist_codegen


def fun_codegen(self, regalloc):
    res = magenta(f"\n{self.symbol.name}:\n")
    res += self.body.codegen(regalloc)
    return res


FunctionDef.codegen = fun_codegen


def binstat_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.srca)
    res += regalloc.gen_spill_load_if_necessary(self.srcb)
    ra = regalloc.get_register_for_variable(self.srca)
    rb = regalloc.get_register_for_variable(self.srcb)
    rd = regalloc.get_register_for_variable(self.dest)

    param = f"{ra}, {rb}"

    # algebric operations
    if self.op == "plus":
        res += ii(f"{yellow('add')} {rd}, {param}\n")
    elif self.op == "minus":
        res += ii(f"{yellow('sub')} {rd}, {param}\n")
    elif self.op == "times":
        res += ii(f"{yellow('mul')} {rd}, {param}\n")
    elif self.op == "slash":
        # XXX: this should never happen, since there is no "div" instruction in armv6
        pass
    elif self.op == "shl":
        res += ii(f"{yellow('lsl')} {rd}, {param}\n")
    elif self.op == "shr":
        res += ii(f"{yellow('lsr')} {rd}, {param}\n")
    elif self.op == "mod":
        res += ii(f"{yellow('add')} {rd}, {param}\n")
        res += ii(f"{yellow('sub')} {get_register_string(REG_SCRATCH)}, {rb}, #{italic('1')}\n")
        res += ii(f"{yellow('and')} {rd}, {rd}, {get_register_string(REG_SCRATCH)}\n")

    # conditional operations
    elif self.op == "eql":
        res += ii(f"{yellow('cmp')} {param}\n")
        res += ii(f"{blue('moveq')} {rd}, #{italic('1')}\n")
        res += ii(f"{blue('movne')} {rd}, #{italic('0')}\n")
    elif self.op == "neq":
        res += ii(f"{yellow('cmp')} {param}\n")
        res += ii(f"{blue('moveq')} {rd}, #{italic('0')}\n")
        res += ii(f"{blue('movne')} {rd}, #{italic('1')}\n")
    elif self.op == "lss":
        res += ii(f"{yellow('cmp')} {param}\n")
        res += ii(f"{blue('movlt')} {rd}, #{italic('1')}\n")
        res += ii(f"{blue('movge')} {rd}, #{italic('0')}\n")
    elif self.op == "leq":
        res += ii(f"{yellow('cmp')} {param}\n")
        res += ii(f"{blue('movle')} {rd}, #{italic('1')}\n")
        res += ii(f"{blue('movgt')} {rd}, #{italic('0')}\n")
    elif self.op == "gtr":
        res += ii(f"{yellow('cmp')} {param}\n")
        res += ii(f"{blue('movgt')} {rd}, #{italic('1')}\n")
        res += ii(f"{blue('movle')} {rd}, #{italic('0')}\n")
    elif self.op == "geq":
        res += ii(f"{yellow('cmp')} {param}\n")
        res += ii(f"{blue('movge')} {rd}, #{italic('1')}\n")
        res += ii(f"{blue('movlt')} {rd}, #{italic('0')}\n")

    # logic operations
    elif self.op == "and":
        res += ii(f"{yellow('and')} {rd}, {param}\n")
    elif self.op == "or":
        res += ii(f"{yellow('orr')} {rd}, {param}\n")

    else:
        raise RuntimeError(f"Operation {self.op} unexpected")

    return res + regalloc.gen_spill_store_if_necessary(self.dest)


BinStat.codegen = binstat_codegen


def print_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rp = regalloc.get_register_for_variable(self.src)

    res += save_regs(REGS_CALLERSAVE)
    res += ii(f"{blue('mov')} {get_register_string(0)}, {rp}\n")
    if self.newline:
        res += ii(f"{blue('mov')} {get_register_string(1)}, #{italic(1)}\n")
    else:
        res += ii(f"{blue('mov')} {get_register_string(1)}, #{italic(0)}\n")
    if self.print_type == TYPENAMES['char']:
        res += ii(f"{red('bl')} {magenta('__pl0_print_string')}\n")
    elif self.print_type == TYPENAMES['boolean']:
        res += ii(f"{red('bl')} {magenta('__pl0_print_boolean')}\n")
    elif self.print_type == TYPENAMES['ubyte']:
        res += ii(f"{red('bl')} {magenta('__pl0_print_unsigned_byte')}\n")
    elif self.print_type == TYPENAMES['ushort']:
        res += ii(f"{red('bl')} {magenta('__pl0_print_unsigned_short')}\n")
    elif self.print_type == TYPENAMES['byte']:
        res += ii(f"{red('bl')} {magenta('__pl0_print_byte')}\n")
    elif self.print_type == TYPENAMES['short']:
        res += ii(f"{red('bl')} {magenta('__pl0_print_short')}\n")
    else:
        res += ii(f"{red('bl')} {magenta('__pl0_print_integer')}\n")
    res += restore_regs(REGS_CALLERSAVE)
    return res


PrintStat.codegen = print_codegen


def read_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)

    # punch a hole in the saved registers if one of them is the destination
    # of this "instruction"
    saved_regs = list(REGS_CALLERSAVE)
    if regalloc.var_to_reg[self.dest] in saved_regs:
        saved_regs.remove(regalloc.var_to_reg[self.dest])

    res = save_regs(saved_regs)
    res += ii(f"{red('bl')} {magenta('__pl0_read')}\n")
    res += ii(f"{blue('mov')} {rd}, {get_register_string(0)}\n")
    res += restore_regs(saved_regs)
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


ReadStat.codegen = read_codegen


# TODO: documentation on the ABI
def call_codegen(call, regalloc):
    res = ""

    # add space on the stack for the return values
    if len(call.returns) > 0:
        res += ii(f"{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{len(call.returns) * -4}')}\n")

    res += save_regs(REGS_CALLERSAVE)

    num_stack_parameters = len(call.parameters[4:])

    # push on the stack all parameters after the first four
    for param_to_put_in_the_stack in call.parameters[4:]:
        res += regalloc.gen_spill_load_if_necessary(param_to_put_in_the_stack)
        res += ii(f"{cyan('push')} {{{regalloc.get_register_for_variable(param_to_put_in_the_stack)}}}\n")

    # put the first 4 parameters in r0-r3
    for i in range(len(call.parameters[:4]) - 1, -1, -1):
        res += regalloc.gen_spill_load_if_necessary(call.parameters[i])
        reg = get_register_string(i)
        var = regalloc.get_register_for_variable(call.parameters[i])

        if remove_formatting(var) not in ['r0', 'r1', 'r2', 'r3']:
            res += ii(f"{blue('mov')} {reg}, {var}\n")
        else:
            # XXX: weird hack to resolve data dependencies:
            #      we have to get this value from one of r0-r3,
            #      but we may have already modified it; to solve this,
            #      use the caller saved register we just pushed on the stack
            pos = ['r0', 'r1', 'r2', 'r3'].index(remove_formatting(var))
            res += ii(f"{blue('ldr')} {reg}, [{get_register_string(REG_SP)}, #{4 * (pos + num_stack_parameters)}]\n")

    res += load_static_chain_pointer(call)

    res += ii(f"{red('bl')} {magenta(call.target.name)}\n")

    # put the first 4 return values from r0-r3 on the stack
    for i in range(len(call.returns[:4]) - 1, -1, -1):
        pos = 4 * (i + 4 + num_stack_parameters)  # TODO documentation
        res += ii(f"{blue('str')} {get_register_string(i)}, [{get_register_string(REG_SP)}, #{pos}]\n")

    # pop the parameters pushed previously
    for param_to_put_in_the_stack in list(reversed(call.parameters[4:])):
        res += ii(f"{cyan('pop')} {{{regalloc.get_register_for_variable(param_to_put_in_the_stack)}}}\n")
        res += regalloc.gen_spill_store_if_necessary(param_to_put_in_the_stack)

    res += restore_regs(REGS_CALLERSAVE)

    # finally, get the return values from the stack in the correct registers
    for i in range(len(call.returns)):
        if call.returns[i] != '_':
            reg = regalloc.get_register_for_variable(call.returns[i])
            res += ii(f"{cyan('pop')} {{{reg}}}\n")
            res += regalloc.gen_spill_store_if_necessary(call.returns[i])
        else:
            res += ii(f"{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{4}')}\n")

    return res


def branch_codegen(self, regalloc):
    res = ""

    if self.target is not None and not self.is_call():
        # just a branch

        target_label = magenta(self.target.name)
        if self.cond is None:
            return ii(f"{red('b')} {target_label}\n")
        else:
            res += regalloc.gen_spill_load_if_necessary(self.cond)
            rcond = regalloc.get_register_for_variable(self.cond)

            res += ii(f"{red('tst')} {rcond}, {rcond}\n")
            op = red("beq" if self.negcond else "bne")
            res += ii(f"{op} {target_label}\n")
            return res

    elif self.target is None:
        # this branch is a return

        # save on the caller stack all return values after the first four
        for i in range(len(self.returns[4:]) - 1, -1, -1):
            ret = self.returns[4:][i]
            res += regalloc.gen_spill_load_if_necessary(ret)
            pos = CALL_OFFSET + 4 * (4 + i + len(self.parameters[4:]))  # TODO: documentation
            res += ii(f"{blue('str')} {regalloc.get_register_for_variable(ret)}, [{get_register_string(REG_FP)}, #{pos}]\n")

        # XXX: this is a hack: to avoid data dependencies, like `mov r0, r1; mov r1, r0`,
        #      push the 4 registers with the return value, then pop them in r0-r3
        for i in range(len(self.returns[:4])):
            ret = self.returns[i]
            res += regalloc.gen_spill_load_if_necessary(ret)
            res += ii(f"{cyan('push')} {{{regalloc.get_register_for_variable(ret)}}}\n")

        for i in range(len(self.returns[:4]) - 1, -1, -1):
            res += ii(f"{cyan('pop')} {{{get_register_string(i)}}}\n")

        res += ii(f"{blue('mov')} {get_register_string(REG_SP)}, {get_register_string(REG_FP)}\n")
        res += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        res += ii(f"{red('bx')} {get_register_string(REG_LR)}\n")
        return res

    # this branch is a call
    return call_codegen(self, regalloc)


BranchStat.codegen = branch_codegen


def emptystat_codegen(self, regalloc):
    return ii(f"{comment('Empty statement')}")


EmptyStat.codegen = emptystat_codegen


def ldptrto_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)
    res = ''

    alloc_info = self.symbol.allocinfo
    if isinstance(alloc_info, LocalSymbolLayout):
        res = ii(f"{yellow('add')} {rd}, {get_register_string(REG_FP)}, #{green(f'{alloc_info.symname}')}\n")
    else:
        res = ii(f"{blue('ldr')} {rd}, ={magenta(f'{alloc_info.symname}')}\n")
    return res + regalloc.gen_spill_store_if_necessary(self.dest)


LoadPtrToSym.codegen = ldptrto_codegen


def storestat_codegen(self, regalloc):
    res = ''

    if self.dest.alloct == 'reg' and self.symbol.alloct == 'reg' and not self.dest.is_pointer():
        res += regalloc.gen_spill_load_if_necessary(self.symbol)
        res += ii(f"{blue('mov')} {regalloc.get_register_for_variable(self.dest)}, {regalloc.get_register_for_variable(self.symbol)}\n")
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
            res = ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, ={green(f'{alloc_info.symname}')}\n")
            dest = f"[{get_register_string(REG_SCRATCH)}]"

    # XXX: not entirely sure about this
    if self.dest.is_array():
        desttype = PointerType(self.dest.stype.basetype)
    elif self.dest.is_pointer():
        desttype = self.dest.stype.pointstotype
    else:
        desttype = self.dest.stype

    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]

    res += regalloc.gen_spill_load_if_necessary(self.symbol)
    rsrc = regalloc.get_register_for_variable(self.symbol)

    res += ii(f"{blue(f'str{typeid}')} {rsrc}, {dest}\n")
    return res


StoreStat.codegen = storestat_codegen


def loadstat_codegen(self, regalloc):
    res = ''

    if self.dest.alloct == 'reg' and self.symbol.alloct == 'reg' and not self.symbol.is_pointer():
        res += regalloc.gen_spill_load_if_necessary(self.symbol)
        res += ii(f"{blue('mov')} {regalloc.get_register_for_variable(self.dest)}, {regalloc.get_register_for_variable(self.symbol)}\n")
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
            res = ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, ={green(f'{alloc_info.symname}')}\n")
            src = f"[{get_register_string(REG_SCRATCH)}]"

    # XXX: not entirely sure about this
    if self.symbol.is_array():
        desttype = PointerType(self.symbol.stype.basetype)
    elif self.symbol.is_pointer():
        desttype = self.symbol.stype.pointstotype
    else:
        desttype = self.symbol.stype

    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]
    if typeid != '' and 'unsigned' not in desttype.qualifiers:
        typeid = f"s{typeid}"

    rdst = regalloc.get_register_for_variable(self.dest)
    res += ii(f"{blue(f'ldr{typeid}')} {rdst}, {src}\n")
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


LoadStat.codegen = loadstat_codegen


def loadimm_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)
    res = ''

    if self.val == "True":
        self.val = 1
    elif self.val == "False":
        self.val = 0

    if self.val >= -256 and self.val < 256:
        if self.val < 0:
            rv = -self.val - 1
            op = f"{blue('mvn')}"
        else:
            rv = self.val
            op = f"{blue('mov')}"

        res += ii(f"{op} {rd}, #{italic(f'{rv}')}\n")
    else:
        res += ii(f"{blue('ldr')} {rd}, =#{italic(f'{self.val}')}\n")

    return res + regalloc.gen_spill_store_if_necessary(self.dest)


LoadImmStat.codegen = loadimm_codegen


def unarystat_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rs = regalloc.get_register_for_variable(self.src)
    rd = regalloc.get_register_for_variable(self.dest)

    # algebric operations
    if self.op == 'plus':
        if rs != rd:
            res += ii(f"{blue('mov')} {rd}, {rs}\n")
    elif self.op == 'minus':
        res += ii(f"{blue('mvn')} {rd}, {rs}\n")
        res += ii(f"{yellow('add')} {rd}, {rd}, #{italic('1')}\n")

    # conditional operations
    elif self.op == 'odd':
        res += ii(f"{yellow('and')} {rd}, {rs}, #{italic('1')}\n")

    # logic operations
    elif self.op == 'not':
        res += ii(f"{blue('cmp')} {rs}, #{italic('0')}\n")
        res += ii(f"{blue('moveq')} {rd}, #{italic('1')}\n")
        res += ii(f"{blue('movne')} {rd}, #{italic('0')}\n")

    else:
        raise RuntimeError(f"Unexpected operation {self.op}")

    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


UnaryStat.codegen = unarystat_codegen


def generate_data_section():
    res = ii(".data\n")
    for symbol in DataSymbolTable.get_data_symtab():
        if symbol.is_string() and symbol.value is not None:
            res += ii(f"{symbol.name}: .asciz \"{symbol.value}\"\n")
        else:
            raise NotImplementedError("Don't have implemented storing non-string values is .data section")

    return res


def generate_code(program, regalloc):
    res = generate_data_section()
    res += ii(".text\n")
    res += ii(".arch armv6\n")
    res += ii(".syntax unified\n")
    return res + program.codegen(regalloc)
