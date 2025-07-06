#!/usr/bin/env python3

"""Code generation methods for all low-level nodes in the IR.
Codegen functions return a string, consisting of the assembly code they
correspond to. Alternatively, they can return a list where:
 - the first element is the assembly code
 - the second element is extra assembly code to be appended at the end of
   the code of the function they are contained in
This feature can be used only by IR nodes that are contained in a Block, and
is used for adding constant literals."""

from codegenhelp import comment, codegen_append, get_register_string, save_regs, restore_regs, REGS_CALLEESAVE, REGS_CALLERSAVE, REG_SP, REG_FP, REG_LR, REG_SCRATCH, check_if_variable_needs_static_link
from datalayout import LocalSymbolLayout
from ir import IRNode, Symbol, Block, BranchStat, DefinitionList, FunctionDef, BinStat, PrintCommand, ReadCommand, EmptyStat, LoadPtrToSym, PointerType, StoreStat, LoadStat, SaveSpaceStat, LoadImmStat, UnaryStat
from logger import red, green, yellow, blue, magenta, cyan, italic

localconsti = 0


def new_local_const_label():
    global localconsti
    const_label = green(f".const{localconsti}")
    localconsti += 1
    return const_label


def new_local_const(val):
    label = new_local_const_label()
    trail = f"{magenta(f'{label}')}:\n{' ' * 4}.word {val}\n"
    return label, trail


def symbol_codegen(self, regalloc):
    if self.allocinfo is None:
        return ""
    if not isinstance(self.allocinfo, LocalSymbolLayout):
        return f"{' ' * 4}.comm {green(f'{self.allocinfo.symname}')}, {self.allocinfo.bsize}\n"
    else:
        return f"{' ' * 4}.equ {green(f'{self.allocinfo.symname}')}, {self.allocinfo.fpreloff}\n"


Symbol.codegen = symbol_codegen


def irnode_codegen(self, regalloc):
    res = [f"{' ' * 4}{comment(f'IRNode {self.type()}, {id(self)}')}", '']
    if "children" in dir(self) and len(self.children):
        for node in self.children:
            try:
                try:
                    label = node.get_label()
                    res[0] += magenta(f"{' ' * 2}{label.name}:\n")
                except Exception:
                    pass
                res = codegen_append(res, node.codegen(regalloc))
            except RuntimeError as e:
                raise RuntimeError(f"Node {node.type()}, {id(node)} did not generate any code; error: {e}")
    return res


IRNode.codegen = irnode_codegen


def block_codegen(self, regalloc):
    res = [f"{' ' * 4}{comment('block')}", '']
    for sym in self.symtab:
        res = codegen_append(res, sym.codegen(regalloc))

    if self.parent is None:
        res[0] += f"{' ' * 4}.global {magenta('__pl0_start')}\n\n"
        res[0] += magenta("__pl0_start:\n")

    # prelude
    res[0] += save_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
    res[0] += f"{' ' * 4}{blue('mov')} {get_register_string(REG_FP)}, {get_register_string(REG_SP)}\n"
    stacksp = self.stackroom + regalloc.spill_room()
    res[0] += f"{' ' * 4}{yellow('sub')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{stacksp}')}\n"

    regalloc.enter_function_body(self)
    try:
        res = codegen_append(res, self.body.codegen(regalloc))
    except AttributeError:
        pass

    last_statement_of_block = self.body.children[-1]
    if type(last_statement_of_block) == BranchStat and last_statement_of_block.target is None:
        # optmization: if the last statement is a return this instructions are useless
        pass
    else:
        res[0] += f"{' ' * 4}{blue('mov')} {get_register_string(REG_SP)}, {get_register_string(REG_FP)}\n"
        res[0] += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        res[0] += f"{' ' * 4}{red('bx')} {get_register_string(REG_LR)}\n"

    res[0] = res[0] + res[1]
    res[1] = ''

    try:
        res = codegen_append(res, self.defs.codegen(regalloc))
    except AttributeError:
        pass

    return res[0] + res[1]


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
    if self.op == "plus":
        res += f"{' ' * 4}{yellow('add')} {rd}, {param}\n"
    elif self.op == "minus":
        res += f"{' ' * 4}{yellow('sub')} {rd}, {param}\n"
    elif self.op == "times":
        res += f"{' ' * 4}{yellow('mul')} {rd}, {param}\n"
    elif self.op == "slash":
        res += f"{' ' * 4}{yellow('div')} {rd}, {param}\n"
    elif self.op == "shl":
        res += f"{' ' * 4}{yellow('lsl')} {rd}, {param}\n"
    elif self.op == "shr":
        res += f"{' ' * 4}{yellow('lsr')} {rd}, {param}\n"
    elif self.op == "mod":
        res += f"{' ' * 4}{yellow('add')} {rd}, {param}\n"
        res += f"{' ' * 4}{yellow('sub')} {get_register_string(REG_SCRATCH)}, {rb}, #{italic('1')}\n"
        res += f"{' ' * 4}{yellow('and')} {rd}, {rd}, {get_register_string(REG_SCRATCH)}\n"
    elif self.op == "eql":
        res += f"{' ' * 4}{yellow('cmp')} {param}\n"
        res += f"{' ' * 4}{blue('moveq')} {rd}, #{italic('1')}\n"
        res += f"{' ' * 4}{blue('movne')} {rd}, #{italic('0')}\n"
    elif self.op == "neq":
        res += f"{' ' * 4}{yellow('cmp')} {param}\n"
        res += f"{' ' * 4}{blue('moveq')} {rd}, #{italic('0')}\n"
        res += f"{' ' * 4}{blue('movne')} {rd}, #{italic('1')}\n"
    elif self.op == "lss":
        res += f"{' ' * 4}{yellow('cmp')} {param}\n"
        res += f"{' ' * 4}{blue('movlt')} {rd}, #{italic('1')}\n"
        res += f"{' ' * 4}{blue('movge')} {rd}, #{italic('0')}\n"
    elif self.op == "leq":
        res += f"{' ' * 4}{yellow('cmp')} {param}\n"
        res += f"{' ' * 4}{blue('movle')} {rd}, #{italic('1')}\n"
        res += f"{' ' * 4}{blue('movgt')} {rd}, #{italic('0')}\n"
    elif self.op == "gtr":
        res += f"{' ' * 4}{yellow('cmp')} {param}\n"
        res += f"{' ' * 4}{blue('movgt')} {rd}, #{italic('1')}\n"
        res += f"{' ' * 4}{blue('movle')} {rd}, #{italic('0')}\n"
    elif self.op == "geq":
        res += f"{' ' * 4}{yellow('cmp')} {param}\n"
        res += f"{' ' * 4}{blue('movge')} {rd}, #{italic('1')}\n"
        res += f"{' ' * 4}{blue('movlt')} {rd}, #{italic('0')}\n"
    else:
        raise RuntimeError(f"Operation {self.op} unexpected")

    return res + regalloc.gen_spill_store_if_necessary(self.dest)


BinStat.codegen = binstat_codegen


def print_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rp = regalloc.get_register_for_variable(self.src)

    res += save_regs(REGS_CALLERSAVE)
    res += f"{' ' * 4}{blue('mov')} {get_register_string(0)}, {rp}\n"
    res += f"{' ' * 4}{red('bl')} {magenta('__pl0_print')}\n"
    res += restore_regs(REGS_CALLERSAVE)
    return res


PrintCommand.codegen = print_codegen


def read_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)

    # punch a hole in the saved registers if one of them is the destination
    # of this "instruction"
    saved_regs = list(REGS_CALLERSAVE)
    if regalloc.var_to_reg[self.dest] in saved_regs:
        saved_regs.remove(regalloc.var_to_reg[self.dest])

    res = save_regs(saved_regs)
    res += f"{' ' * 4}{red('bl')} {magenta('__pl0_read')}\n"
    res += f"{' ' * 4}{blue('mov')} {rd}, {get_register_string(0)}\n"
    res += restore_regs(saved_regs)
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


ReadCommand.codegen = read_codegen


def branch_codegen(self, regalloc):
    if self.target is None:
        # this branch is a return
        res = f"{' ' * 4}{blue('mov')} {get_register_string(REG_SP)}, {get_register_string(REG_FP)}\n"
        res += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        res += f"{' ' * 4}{red('bx')} {get_register_string(REG_LR)}\n"
        return res

    target_label = magenta(self.target.name)
    if not self.is_call:
        # just a branch
        if self.cond is None:
            return f"{' ' * 4}{red('b')} {target_label}\n"
        else:
            res = regalloc.gen_spill_load_if_necessary(self.cond)
            rcond = regalloc.get_register_for_variable(self.cond)

            res += f"{' ' * 4}{red('tst')} {rcond}, {rcond}\n"
            op = red("beq" if self.negcond else "bne")
            res += f"{' ' * 4}{op} {target_label}\n"
            return res

    else:
        # this branch is a call
        if self.cond is None:
            res = save_regs(REGS_CALLERSAVE)
            res += f"{' ' * 4}{red('bl')} {target_label}\n"
            res += restore_regs(REGS_CALLERSAVE)

            # restore space left by the parameters
            if self.space_needed_for_parameters > 0:
                res += f"{' ' * 4}{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{self.space_needed_for_parameters}')}\n"

            return res
        else:
            res = regalloc.gen_spill_load_if_necessary(self.cond)
            rcond = regalloc.get_register_for_variable(self.cond)

            res += f"{' ' * 4}{red('tst')} {rcond}, {rcond}\n"

            # TODO: test if this is correct
            op = red("beq" if self.negcond else "bne")
            res += f"{' ' * 4}{op} {rcond}, 1f\n"

            res += save_regs(REGS_CALLERSAVE)
            res += f"{' ' * 4}{red('bl')} {target_label}\n"
            res += restore_regs(REGS_CALLERSAVE)

            # restore space left by the parameters
            if self.space_needed_for_parameters > 0:
                res += f"{' ' * 4}{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{self.space_needed_for_parameters}')}\n"

            # TODO: what does this mean?
            res += '1:'
            return res


BranchStat.codegen = branch_codegen


def emptystat_codegen(self, regalloc):
    return f"{' ' * 4}{comment('Empty statement')}"


EmptyStat.codegen = emptystat_codegen


def ldptrto_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)
    res = ''
    trail = ''

    alloc_info = self.symbol.allocinfo
    if type(alloc_info) is LocalSymbolLayout:
        off = alloc_info.fpreloff
        if off > 0:
            res = f"{' ' * 4}{yellow('add')} {rd}, {get_register_string(REG_FP)}, #{italic(f'{off}')}\n"
        else:
            res = f"{' ' * 4}{yellow('sub')} {rd}, {get_register_string(REG_FP)}, #{italic(f'{-off}')}\n"
    else:
        label, trail = new_local_const(alloc_info.symname)
        res = f"{' ' * 4}{blue('ldr')} {rd}, {label}\n"
    return [res + regalloc.gen_spill_store_if_necessary(self.dest), trail]


LoadPtrToSym.codegen = ldptrto_codegen


def storestat_codegen(self, regalloc):
    res = ''
    trail = ''

    if self.dest.alloct == 'param':
        res += f"{' ' * 4}{cyan('push')} {{{regalloc.get_register_for_variable(self.symbol)}}}\n"
        return [res, trail]

    elif self.dest.alloct == 'reg' and self.symbol.alloct == 'reg':
        res += f"{' ' * 4}{blue('mov')} {regalloc.get_register_for_variable(self.dest)}, {regalloc.get_register_for_variable(self.symbol)}\n"
        return [res, trail]

    elif self.dest.alloct == 'reg':
        res += regalloc.gen_spill_load_if_necessary(self.dest)
        dest = f"[{regalloc.get_register_for_variable(self.dest)}]"

    else:
        alloc_info = self.dest.allocinfo
        if type(alloc_info) is LocalSymbolLayout:
            static_link = check_if_variable_needs_static_link(self, self.dest)
            if static_link:
                res += static_link
                # if the static link is necessary use the offset contained in the scratch register
                dest = f"[{get_register_string(REG_SCRATCH)}, #{green(f'{alloc_info.symname}')}]"
            else:
                dest = f"[{get_register_string(REG_FP)}, #{green(f'{alloc_info.symname}')}]"

        else:
            label, trail = new_local_const(alloc_info.symname)
            res = f"{' ' * 4}{blue('ldr')} {get_register_string(REG_SCRATCH)}, {label}\n"
            dest = f"[{get_register_string(REG_SCRATCH)}]"

    if type(self.dest.stype) is PointerType:
        desttype = self.dest.stype.pointstotype
    else:
        desttype = self.dest.stype

    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]
    if typeid != '' and 'unsigned' in desttype.qual_list:
        typeid = 's' + type

    res += regalloc.gen_spill_load_if_necessary(self.symbol)
    rsrc = regalloc.get_register_for_variable(self.symbol)

    res += f"{' ' * 4}{blue('str')}{typeid} {rsrc}, {dest}\n"
    return [res, trail]


StoreStat.codegen = storestat_codegen


def loadstat_codegen(self, regalloc):
    res = ''
    trail = ''

    if self.symbol.alloct == 'return':
        res += f"{' ' * 4}{cyan('pop')} {{{regalloc.get_register_for_variable(self.dest)}}}\n"
        return [res, trail]

    elif self.dest.alloct == 'reg' and self.symbol.alloct == 'reg':
        res += f"{' ' * 4}{blue('mov')} {regalloc.get_register_for_variable(self.dest)}, {regalloc.get_register_for_variable(self.symbol)}\n"
        return [res, trail]

    elif self.symbol.alloct == 'reg':
        res += regalloc.gen_spill_load_if_necessary(self.symbol)
        src = f"[{regalloc.get_register_for_variable(self.symbol)}]"

    else:
        alloc_info = self.symbol.allocinfo
        if type(alloc_info) is LocalSymbolLayout:
            static_link = check_if_variable_needs_static_link(self, self.symbol)
            if static_link:
                res += static_link
                # if the static link is necessary use the offset contained in the scratch register
                src = f"[{get_register_string(REG_SCRATCH)}, #{green(f'{alloc_info.symname}')}]"
            else:
                src = f"[{get_register_string(REG_FP)}, #{green(f'{alloc_info.symname}')}]"

        else:
            label, trail = new_local_const(alloc_info.symname)
            res = f"{' ' * 4}{blue('ldr')} {get_register_string(REG_SCRATCH)}, {label}\n"
            src = f"[{get_register_string(REG_SCRATCH)}]"

    if type(self.symbol.stype) is PointerType:
        desttype = self.symbol.stype.pointstotype
    else:
        desttype = self.symbol.stype
    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]
    if typeid != '' and 'unsigned' in desttype.qual_list:
        typeid = 's' + type

    rdst = regalloc.get_register_for_variable(self.dest)
    res += f"{' ' * 4}{blue('ldr')} {typeid} {rdst}, {src}\n"
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return [res, trail]


LoadStat.codegen = loadstat_codegen


def savespacestat_codegen(self, regalloc):
    res = f"{' ' * 4}{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{self.space_needed}')}"

    if self.space_needed > 0:
        res += f" {comment('ignoring a return value')}"
    else:
        res += f" {comment('saving space for return values')}"

    return res


SaveSpaceStat.codegen = savespacestat_codegen


def loadimm_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)
    res = ''
    trail = ''

    if self.val >= -256 and self.val < 256:
        if self.val < 0:
            rv = -self.val - 1
            op = f"{blue('mvn')}"
        else:
            rv = self.val
            op = f"{blue('mov')}"

        res += f"{' ' * 4}{op} {rd}, #{italic(f'{rv}')}\n"
    else:
        label, trail = new_local_const(repr(self.val))
        res += f"{' ' * 4}{blue('ldr')} {rd}, {label}\n"

    return [res + regalloc.gen_spill_store_if_necessary(self.dest), trail]


LoadImmStat.codegen = loadimm_codegen


def unarystat_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rs = regalloc.get_register_for_variable(self.src)
    rd = regalloc.get_register_for_variable(self.dest)

    if self.op == 'plus':
        if rs != rd:
            res += f"{' ' * 4}{blue('mov')} {rd}, {rs}\n"
    elif self.op == 'minus':
        res += f"{' ' * 4}{blue('mvn')} {rd}, {rs}\n"
        res += f"{' ' * 4}{yellow('add')} {rd}, {rd}, #{italic('1')}\n"
    elif self.op == 'odd':
        res += f"{' ' * 4}{yellow('and')} {rd}, {rs}, #{italic('1')}\n"
    else:
        raise RuntimeError(f"Unexpected operation {self.op}")

    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


UnaryStat.codegen = unarystat_codegen


def generate_code(program, regalloc):
    res = f"{' ' * 4}.text\n"
    res += f"{' ' * 4}.arch armv6\n"
    res += f"{' ' * 4}.syntax unified\n"
    return res + program.codegen(regalloc)
