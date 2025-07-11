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
from ir import IRNode, Symbol, Block, BranchStat, DefinitionList, FunctionDef, BinStat, PrintCommand, ReadCommand, EmptyStat, LoadPtrToSym, ArrayType, PointerType, StoreStat, LoadStat, SaveSpaceStat, LoadImmStat, UnaryStat, DataSymbolTable
from logger import ii, hi, red, green, yellow, blue, magenta, cyan, italic

localconsti = 0


def new_local_const_label():
    global localconsti
    const_label = green(f".const{localconsti}")
    localconsti += 1
    return const_label


# keep track of already given consts labels
local_consts = {}


def new_local_const(val):
    if val in local_consts:
        return local_consts[val], ""

    label = new_local_const_label()
    trail = f"{magenta(f'{label}')}:\n"
    trail += ii(f".word {val}\n")

    local_consts[val] = label

    return label, trail


def symbol_codegen(self, regalloc):
    if self.allocinfo is None:
        return ""
    if not isinstance(self.allocinfo, LocalSymbolLayout):
        return ii(f".comm {green(f'{self.allocinfo.symname}')}, {self.allocinfo.bsize}\n")
    else:
        return ii(f".equ {green(f'{self.allocinfo.symname}')}, {self.allocinfo.fpreloff}\n")


Symbol.codegen = symbol_codegen


def irnode_codegen(self, regalloc):
    res = [ii(f"{comment(f'IRNode {self.type()}, {id(self)}')}"), '']
    if "children" in dir(self) and len(self.children):
        for node in self.children:
            try:
                try:
                    label = node.get_label()
                    res[0] += hi(magenta(f"{label.name}:\n"))
                except Exception:
                    pass
                res = codegen_append(res, node.codegen(regalloc))
            except RuntimeError as e:
                raise RuntimeError(f"Node {node.type()}, {id(node)} did not generate any code; error: {e}")
    return res


IRNode.codegen = irnode_codegen


def block_codegen(self, regalloc):
    res = [ii(f"{comment('block')}"), '']
    for sym in self.symtab:
        res = codegen_append(res, sym.codegen(regalloc))

    if self.parent is None:
        res[0] += ii(f".global {magenta('__pl0_start')}\n\n")
        res[0] += magenta("__pl0_start:\n")

    # prelude
    res[0] += save_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
    res[0] += ii(f"{blue('mov')} {get_register_string(REG_FP)}, {get_register_string(REG_SP)}\n")
    stacksp = self.stackroom + regalloc.spill_room()
    res[0] += ii(f"{yellow('sub')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{stacksp}')}\n")

    regalloc.enter_function_body(self)
    try:
        res = codegen_append(res, self.body.codegen(regalloc))
    except AttributeError as e:
        print(red("Can't execute codegen"))
        raise RuntimeError(e)

    last_statement_of_block = self.body.children[-1]
    if type(last_statement_of_block) == BranchStat and last_statement_of_block.target is None:
        # optmization: if the last statement is a return this instructions are useless
        pass
    else:
        res[0] += ii(f"{blue('mov')} {get_register_string(REG_SP)}, {get_register_string(REG_FP)}\n")
        res[0] += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        res[0] += ii(f"{red('bx')} {get_register_string(REG_LR)}\n")

    res[0] = res[0] + res[1]
    res[1] = ''

    try:
        res = codegen_append(res, self.defs.codegen(regalloc))
    except AttributeError as e:
        print(red("Can't execute codegen"))
        raise RuntimeError(e)

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
    else:
        raise RuntimeError(f"Operation {self.op} unexpected")

    return res + regalloc.gen_spill_store_if_necessary(self.dest)


BinStat.codegen = binstat_codegen


def print_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rp = regalloc.get_register_for_variable(self.src)

    res += save_regs(REGS_CALLERSAVE)
    res += ii(f"{blue('mov')} {get_register_string(0)}, {rp}\n")
    if self.print_string:
        res += ii(f"{red('bl')} {magenta('__pl0_print_string')}\n")
    else:
        res += ii(f"{red('bl')} {magenta('__pl0_print_digit')}\n")
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
    res += ii(f"{red('bl')} {magenta('__pl0_read')}\n")
    res += ii(f"{blue('mov')} {rd}, {get_register_string(0)}\n")
    res += restore_regs(saved_regs)
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


ReadCommand.codegen = read_codegen


def branch_codegen(self, regalloc):
    if self.target is None:
        # this branch is a return
        res = ii(f"{blue('mov')} {get_register_string(REG_SP)}, {get_register_string(REG_FP)}\n")
        res += restore_regs(REGS_CALLEESAVE + [REG_FP, REG_LR])
        res += ii(f"{red('bx')} {get_register_string(REG_LR)}\n")
        return res

    target_label = magenta(self.target.name)
    if not self.is_call:
        # just a branch
        if self.cond is None:
            return ii(f"{red('b')} {target_label}\n")
        else:
            res = regalloc.gen_spill_load_if_necessary(self.cond)
            rcond = regalloc.get_register_for_variable(self.cond)

            res += ii(f"{red('tst')} {rcond}, {rcond}\n")
            op = red("beq" if self.negcond else "bne")
            res += ii(f"{op} {target_label}\n")
            return res

    else:
        # this branch is a call
        if self.cond is None:
            res = save_regs(REGS_CALLERSAVE)
            res += ii(f"{red('bl')} {target_label}\n")
            res += restore_regs(REGS_CALLERSAVE)

            # restore space left by the parameters
            if self.space_needed_for_parameters > 0:
                res += ii(f"{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{self.space_needed_for_parameters}')}\n")

            return res
        else:
            res = regalloc.gen_spill_load_if_necessary(self.cond)
            rcond = regalloc.get_register_for_variable(self.cond)

            res += ii(f"{red('tst')} {rcond}, {rcond}\n")

            # TODO: test if this is correct
            op = red("beq" if self.negcond else "bne")
            res += ii(f"{op} {rcond}, 1f\n")

            res += save_regs(REGS_CALLERSAVE)
            res += ii(f"{red('bl')} {target_label}\n")
            res += restore_regs(REGS_CALLERSAVE)

            # restore space left by the parameters
            if self.space_needed_for_parameters > 0:
                res += ii(f"{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{self.space_needed_for_parameters}')}\n")

            # TODO: what does this mean?
            res += '1:'
            return res


BranchStat.codegen = branch_codegen


def emptystat_codegen(self, regalloc):
    return ii(f"{comment('Empty statement')}")


EmptyStat.codegen = emptystat_codegen


def ldptrto_codegen(self, regalloc):
    rd = regalloc.get_register_for_variable(self.dest)
    res = ''
    trail = ''

    alloc_info = self.symbol.allocinfo
    if type(alloc_info) is LocalSymbolLayout:
        off = alloc_info.fpreloff
        if off > 0:
            res = ii(f"{yellow('add')} {rd}, {get_register_string(REG_FP)}, #{italic(f'{off}')}\n")
        else:
            res = ii(f"{yellow('sub')} {rd}, {get_register_string(REG_FP)}, #{italic(f'{-off}')}\n")
    else:
        label, trail = new_local_const(alloc_info.symname)
        res = ii(f"{blue('ldr')} {rd}, {label}\n")
    return [res + regalloc.gen_spill_store_if_necessary(self.dest), trail]


LoadPtrToSym.codegen = ldptrto_codegen


def storestat_codegen(self, regalloc):
    res = ''
    trail = ''

    if self.dest.alloct == 'param':
        res += ii(f"{cyan('push')} {{{regalloc.get_register_for_variable(self.symbol)}}}\n")
        return [res, trail]

    elif self.dest.alloct == 'reg' and self.symbol.alloct == 'reg' and not isinstance(self.dest.stype, PointerType):
        res += ii(f"{blue('mov')} {regalloc.get_register_for_variable(self.dest)}, {regalloc.get_register_for_variable(self.symbol)}\n")
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
            res = ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, {label}\n")
            dest = f"[{get_register_string(REG_SCRATCH)}]"

    if type(self.dest.stype) is PointerType:
        desttype = self.dest.stype.pointstotype
    else:
        desttype = self.dest.stype

    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]

    res += regalloc.gen_spill_load_if_necessary(self.symbol)
    rsrc = regalloc.get_register_for_variable(self.symbol)

    res += ii(f"{blue(f'str{typeid}')} {rsrc}, {dest}\n")
    return [res, trail]


StoreStat.codegen = storestat_codegen


def loadstat_codegen(self, regalloc):
    res = ''
    trail = ''

    if self.symbol.alloct == 'return':
        res += ii(f"{cyan('pop')} {{{regalloc.get_register_for_variable(self.dest)}}}\n")
        return [res, trail]

    elif self.dest.alloct == 'reg' and self.symbol.alloct == 'reg' and not isinstance(self.symbol.stype, PointerType):
        res += ii(f"{blue('mov')} {regalloc.get_register_for_variable(self.dest)}, {regalloc.get_register_for_variable(self.symbol)}\n")
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
            res = ii(f"{blue('ldr')} {get_register_string(REG_SCRATCH)}, {label}\n")
            src = f"[{get_register_string(REG_SCRATCH)}]"

    # XXX: not entirely sure about this
    if type(self.symbol.stype) is ArrayType:
        desttype = self.symbol.stype.basetype
        rdst = regalloc.get_register_for_variable(self.dest)
        res += ii(f"{blue(f'mov')} {rdst}, {get_register_string(REG_SCRATCH)}\n")
        return [res, trail]
    elif type(self.symbol.stype) is PointerType:
        desttype = self.symbol.stype.pointstotype
    else:
        desttype = self.symbol.stype

    typeid = ['b', 'h', None, ''][desttype.size // 8 - 1]
    if typeid != '' and 'unsigned' not in desttype.qual_list:
        typeid = f"s{typeid}"

    rdst = regalloc.get_register_for_variable(self.dest)
    res += ii(f"{blue(f'ldr{typeid}')} {rdst}, {src}\n")
    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return [res, trail]


LoadStat.codegen = loadstat_codegen


def savespacestat_codegen(self, regalloc):
    res = ii(f"{yellow('add')} {get_register_string(REG_SP)}, {get_register_string(REG_SP)}, #{italic(f'{self.space_needed}')}")

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

        res += ii(f"{op} {rd}, #{italic(f'{rv}')}\n")
    else:
        label, trail = new_local_const(repr(self.val))
        res += ii(f"{blue('ldr')} {rd}, {label}\n")

    return [res + regalloc.gen_spill_store_if_necessary(self.dest), trail]


LoadImmStat.codegen = loadimm_codegen


def unarystat_codegen(self, regalloc):
    res = regalloc.gen_spill_load_if_necessary(self.src)
    rs = regalloc.get_register_for_variable(self.src)
    rd = regalloc.get_register_for_variable(self.dest)

    if self.op == 'plus':
        if rs != rd:
            res += ii(f"{blue('mov')} {rd}, {rs}\n")
    elif self.op == 'minus':
        res += ii(f"{blue('mvn')} {rd}, {rs}\n")
        res += ii(f"{yellow('add')} {rd}, {rd}, #{italic('1')}\n")
    elif self.op == 'odd':
        res += ii(f"{yellow('and')} {rd}, {rs}, #{italic('1')}\n")
    else:
        raise RuntimeError(f"Unexpected operation {self.op}")

    res += regalloc.gen_spill_store_if_necessary(self.dest)
    return res


UnaryStat.codegen = unarystat_codegen


def generate_data_section():
    res = ii(".data\n")
    for symbol in DataSymbolTable.get_data_symtab():
        if symbol.stype.name == "char":
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
