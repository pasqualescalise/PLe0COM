#!/usr/bin/env python3

"""
LLVM integration: lower the AST to LLVM IR using llvmlite

It uses a different ABI than the one used in the "normal" compiler:
    * nested symbols are passed not using a static chain, but by lambda lifting,
      which means that they are passed as parameters after the "normal" parameters
    * since we can only return one value, in r0, in case of multiple returns we
      return a struct containing all the values, otherwise return the value in r0
"""

from llvmlite import ir

from frontend.ast import Const, Var, ArrayElement, String, BinaryExpr, UnaryExpr, CallStat, IfStat, WhileStat, ForStat, AssignStat, PrintStat, ReadStat, ReturnStat, StatList
from ir.ir import FunctionDef, ArrayType, TYPENAMES
from llvm.llvm_helpers import get_llvm_type_for_return, convert_type_to_llvm_type, mask_number_to_its_type, get_lambda_lifting, get_symbol_reference, add_extern_functions


# if true, stop the codegen of the current StatList
STOP_FLAG = False


def const_llvm_codegen(self, variable_state):
    value = self.value

    if self.value == 'True':
        value = True
    elif self.value == 'False':
        value = False

    return ir.Constant(convert_type_to_llvm_type(self.type), value)


Const.llvm_codegen = const_llvm_codegen


def var_llvm_codegen(self, variable_state):
    symbol = get_symbol_reference(builder, self.symbol, variable_state)

    if self.offset is None:
        if self.symbol.is_string():
            return symbol
        return builder.load(symbol)

    # get a pointer to the array element
    indexes = self.offset.llvm_codegen(variable_state)
    ptr = builder.gep(symbol, [ir.Constant(ir.IntType(32), 0)] + indexes)
    if self.symbol.type.basetype == TYPENAMES['char']:  # string array
        return ptr
    return builder.load(ptr)


Var.llvm_codegen = var_llvm_codegen


# XXX: normally this returns an element of the array, but for
#      LLVM it's easier to return a list of indexes
def array_element_llvm_codegen(self, variable_state):
    indexes = []
    for index in self.children:
        indexes.append(index.llvm_codegen(variable_state))

    return indexes


ArrayElement.llvm_codegen = array_element_llvm_codegen


# TODO: optimization to remove duplicate strings
def string_llvm_codegen(self, variable_state):
    value = bytearray(self.value.encode('raw_unicode_escape').decode('unicode_escape') + "\x00", "utf-8")
    type = convert_type_to_llvm_type(ArrayType(None, [len(value)], TYPENAMES['char']))
    name = module.get_unique_name("data")
    data_variable = ir.GlobalVariable(module, type, name)

    initializer = ir.Constant(type, value)
    data_variable.initializer = initializer

    return data_variable


String.llvm_codegen = string_llvm_codegen


def binary_expr_llvm_codegen(self, variable_state):
    op_a = self.children[0].llvm_codegen(variable_state)
    op_b = self.children[1].llvm_codegen(variable_state)

    smallest_operand = op_a if self.children[0].type.size < self.children[1].type.size else op_b

    if op_a == smallest_operand:
        op_a = mask_number_to_its_type(builder, op_a, op_b.type)
    else:
        op_b = mask_number_to_its_type(builder, op_b, op_a.type)

    match self.operator:
        case 'plus':
            return builder.add(op_a, op_b)
        case 'minus':
            return builder.sub(op_a, op_b)
        case 'times':
            return builder.mul(op_a, op_b)
        case 'slash':
            # XXX: we only do integer divisions now
            if 'unsigned' in self.type.qualifiers:
                return builder.udiv(op_a, op_b)
            return builder.sdiv(op_a, op_b)
        case 'shl':
            return builder.shl(op_a, op_b)
        case 'shr':
            return builder.ashr(op_a, op_b)
        case 'mod':
            if 'unsigned' in self.type.qualifiers:
                return builder.urem(op_a, op_b)
            return builder.srem(op_a, op_b)

        case 'eql':
            if 'unsigned' in self.type.qualifiers:
                return builder.icmp_unsigned("==", op_a, op_b)
            return builder.icmp_signed("==", op_a, op_b)
        case 'neq':
            if 'unsigned' in self.type.qualifiers:
                return builder.icmp_unsigned("!=", op_a, op_b)
            return builder.icmp_signed("!=", op_a, op_b)
        case 'lss':
            if 'unsigned' in self.type.qualifiers:
                return builder.icmp_unsigned("<", op_a, op_b)
            return builder.icmp_signed("<", op_a, op_b)
        case 'leq':
            if 'unsigned' in self.type.qualifiers:
                return builder.icmp_unsigned("<=", op_a, op_b)
            return builder.icmp_signed("<=", op_a, op_b)
        case 'gtr':
            if 'unsigned' in self.type.qualifiers:
                return builder.icmp_unsigned(">", op_a, op_b)
            return builder.icmp_signed(">", op_a, op_b)
        case 'geq':
            if 'unsigned' in self.type.qualifiers:
                return builder.icmp_unsigned(">=", op_a, op_b)
            return builder.icmp_signed(">=", op_a, op_b)

        case 'and':
            return builder.and_(op_a, op_b)
        case 'or':
            return builder.or_(op_a, op_b)


BinaryExpr.llvm_codegen = binary_expr_llvm_codegen


def unary_expr_llvm_codegen(self, variable_state):
    operand = self.children[0].llvm_codegen(variable_state)

    match self.operator:
        case 'plus':
            return operand
        case 'minus':
            return builder.neg(operand)

        case 'odd':
            two = mask_number_to_its_type(builder, ir.Constant(ir.IntType(32), 2), operand.type)
            if 'unsigned' in self.children[0].type.qualifiers:
                return builder.trunc(builder.urem(operand, two), ir.IntType(1))
            return builder.trunc(builder.srem(operand, two), ir.IntType(1))
        case 'not':
            true = ir.Constant(ir.IntType(1), 1)
            false = ir.Constant(ir.IntType(1), 0)
            cond = builder.icmp_unsigned("==", operand, false)
            return builder.select(cond, true, false)


UnaryExpr.llvm_codegen = unary_expr_llvm_codegen


def call_stat_llvm_codegen(self, variable_state):
    called_function = module.get_global(self.function_symbol.name)

    parameters = []
    for i in range(len(self.children)):
        parameter = self.children[i]

        if parameter.type.is_numeric():
            type = called_function.args[i].type
            parameters += [mask_number_to_its_type(builder, parameter.llvm_codegen(variable_state), type)]
        elif parameter.type.is_string():
            type = called_function.args[i].type
            parameters += [builder.load(parameter.llvm_codegen(variable_state))]
        else:
            parameters += [parameter.llvm_codegen(variable_state)]

    # if there are any, add lambda lifted parameters
    lambda_lifted_symbols = get_lambda_lifting(self.function_symbol, self.symtab)
    for lambda_lifted_symbol in lambda_lifted_symbols:
        parameters += [get_symbol_reference(builder, lambda_lifted_symbol, variable_state)]

    return_value = builder.call(called_function, tuple(parameters))

    match len(self.returns):
        case 0:
            return

        case 1:
            if self.returns[0] != '_':
                variable_state[self.returns_storage[0]] = return_value

        case _:  # multiple return values, we got them in a struct
            j = 0  # skip dontcares
            for i in range(len(self.returns)):
                if self.returns[i] != '_':
                    element = builder.extract_value(return_value, [i])
                    variable_state[self.returns_storage[j]] = element
                    j += 1


CallStat.llvm_codegen = call_stat_llvm_codegen


# XXX: Elifs looks kinda weird, but their bodies and their conditions must be
#      in different basic blocks since each block ends on a branch
def if_stat_llvm_codegen(self, variable_state):
    # define all the basic blocks
    then_block = builder.append_basic_block(name="then")
    if len(self.children) > 0:
        elifs_blocks = []
        for i in range(len(self.children)):
            elifs_blocks += [builder.append_basic_block(name="elif_condition")]
            elifs_blocks += [builder.append_basic_block(name="elif")]
    if self.elsepart is not None:
        else_block = builder.append_basic_block(name="else")
    endif_block = builder.append_basic_block(name="endif")
    no_endif_block = True  # decides whether or not to put the endif basic block at the end

    # where to go instead of the if
    if len(self.children) > 0:
        next_block = elifs_blocks[0]
    elif self.elsepart is not None:
        next_block = else_block
    else:
        no_endif_block = False
        next_block = endif_block

    # if
    if_condition = self.cond.llvm_codegen(variable_state)
    builder.cbranch(if_condition, then_block, next_block)

    builder.position_at_start(then_block)
    self.thenpart.llvm_codegen(variable_state)
    if not builder.block.is_terminated:
        builder.branch(endif_block)
        no_endif_block = False
    else:
        no_endif_block |= False

    # where to go after the last elif
    if self.elsepart is not None:
        last_block = else_block
    else:
        last_block = endif_block
        no_endif_block = False

    # elifs
    for i in range(0, len(self.children) * 2, 2):  # XXX: conditions and bodies are in two different blocks
        builder.position_at_start(elifs_blocks[i])
        elif_condition = self.children[i // 2].llvm_codegen(variable_state)

        if i == (len(self.children) * 2) - 2:  # last one
            builder.cbranch(elif_condition, elifs_blocks[i + 1], last_block)
        else:
            builder.cbranch(elif_condition, elifs_blocks[i + 1], elifs_blocks[i + 2])

        builder.position_at_start(elifs_blocks[i + 1])
        self.elifspart.children[i // 2].llvm_codegen(variable_state)
        if not builder.block.is_terminated:
            builder.branch(endif_block)
            no_endif_block = False
        else:
            no_endif_block |= False

    # else
    if self.elsepart is not None:
        builder.position_at_start(else_block)
        self.elsepart.llvm_codegen(variable_state)
        if not builder.block.is_terminated:
            builder.branch(endif_block)
            no_endif_block = False
        else:
            no_endif_block |= False

    if no_endif_block:
        builder.function.basic_blocks.remove(endif_block)
        # there is no reason to continue the codegen after this if, since
        # all branches of the if terminate with a return
        global STOP_FLAG
        STOP_FLAG = True
    else:
        builder.position_at_start(endif_block)


IfStat.llvm_codegen = if_stat_llvm_codegen


def while_stat_llvm_codegen(self, variable_state):
    loop_block = builder.append_basic_block(name="loop")
    exit_block = builder.append_basic_block(name="exit")

    loop_condition = self.cond.llvm_codegen(variable_state)
    builder.cbranch(loop_condition, loop_block, exit_block)

    builder.position_at_start(loop_block)
    self.body.llvm_codegen(variable_state)

    if not loop_block.is_terminated:  # there is a return in the body
        loop_condition = self.cond.llvm_codegen(variable_state)
        builder.cbranch(loop_condition, loop_block, exit_block)

    builder.position_at_start(exit_block)


WhileStat.llvm_codegen = while_stat_llvm_codegen


def for_stat_llvm_codegen(self, variable_state):
    entry_block = builder.basic_block

    self.init.llvm_codegen(variable_state)
    first_loop_condition = self.cond.llvm_codegen(variable_state)
    # XXX: the branch to exit is inserted later

    start_loop_body_block = builder.append_basic_block(name="start_loop_body")
    builder.position_at_start(start_loop_body_block)
    self.body.llvm_codegen(variable_state)

    end_loop_body_block = builder.basic_block
    if end_loop_body_block.is_terminated:
        end_loop_body_block = builder.append_basic_block(name="end_loop_body")
    builder.position_at_end(end_loop_body_block)

    self.step.llvm_codegen(variable_state)
    recurring_loop_condition = self.cond.llvm_codegen(variable_state)
    # XXX: the branch to exit is inserted later

    exit_block = builder.append_basic_block(name="exit")

    builder.position_at_end(entry_block)
    builder.cbranch(first_loop_condition, start_loop_body_block, exit_block)
    builder.position_at_end(end_loop_body_block)
    builder.cbranch(recurring_loop_condition, start_loop_body_block, exit_block)

    builder.position_at_start(exit_block)

    if self.epilogue is not None:
        self.epilogue.llvm_codegen(variable_state)


ForStat.llvm_codegen = for_stat_llvm_codegen


def assign_stat_llvm_codegen(self, variable_state):
    remove_after_assignment = False

    try:
        expr = self.expr.llvm_codegen(variable_state)
    except AttributeError as e:
        if e.name == "llvm_codegen":  # expr is a Symbol
            expr = variable_state[self.expr]
            remove_after_assignment = True
        else:
            raise e

    symbol = get_symbol_reference(builder, self.symbol, variable_state)

    if self.symbol.type.is_string():
        # XXX: the bitcast is needed since we can put a smaller array into a bigger one
        builder.store(builder.load(expr), builder.bitcast(symbol, expr.type))
    elif self.offset is None:
        # mask
        masked_expr = mask_number_to_its_type(builder, expr, symbol.type.pointee)
        builder.store(masked_expr, symbol)
    else:
        indexes = self.offset.llvm_codegen(variable_state)
        ptr = builder.gep(symbol, [ir.Constant(ir.IntType(32), 0)] + indexes)

        if self.expr.type.is_string():
            # XXX: the bitcast is needed since we can put a smaller array into a bigger one
            builder.store(builder.load(expr), builder.bitcast(ptr, expr.type))
        else:
            builder.store(mask_number_to_its_type(builder, expr, ptr.type.pointee), ptr)

    # to avoid polluting the variable state, remove the Symbol
    # used only for this assignment
    if remove_after_assignment:
        del variable_state[self.expr]


AssignStat.llvm_codegen = assign_stat_llvm_codegen


def print_stat_llvm_codegen(self, variable_state):
    expr = self.children[0]

    parameters = []
    parameters += [expr.llvm_codegen(variable_state)]
    parameters += [ir.Constant(ir.IntType(32), 1) if self.newline else ir.Constant(ir.IntType(32), 0)]

    match self.print_type:
        case x if x.is_numeric():
            if 'unsigned' in self.print_type.qualifiers:
                parameters[0] = builder.zext(parameters[0], ir.IntType(32))
            else:
                parameters[0] = builder.sext(parameters[0], ir.IntType(32))
            func = module.get_global("__pl0_print_numeric")
        case x if x == TYPENAMES['boolean']:
            parameters[0] = builder.zext(parameters[0], ir.IntType(32))
            func = module.get_global("__pl0_print_boolean")
        case x if isinstance(x, ArrayType) and x.basetype == TYPENAMES['char']:
            parameters[0] = builder.ptrtoint(parameters[0], ir.IntType(32))
            func = module.get_global("__pl0_print_string")
        case _:
            raise NotImplementedError

    builder.call(func, tuple(parameters))


PrintStat.llvm_codegen = print_stat_llvm_codegen


def read_stat_llvm_codegen(self, variable_state):  # TODO: this is not in use now
    func = module.get_global("__pl0_read")
    return builder.call(func, ())


ReadStat.llvm_codegen = read_stat_llvm_codegen


def return_stat_llvm_codegen(self, variable_state):
    returns = [x.llvm_codegen(variable_state) for x in self.children]

    match len(returns):
        case 0:
            builder.ret_void()

        case 1:
            return_value_type = builder.function.return_value.type

            if self.children[0].type.is_numeric():
                builder.ret(mask_number_to_its_type(builder, returns[0], return_value_type))
            elif self.children[0].type.is_string():
                # XXX: the bitcast is needed since we can put a smaller array into a bigger one
                builder.ret(builder.bitcast(returns[0], return_value_type))
            else:
                builder.ret(returns[0])

        case _:  # multiple return values, allocate a struct and return it
            return_value_type = builder.function.return_value.type
            return_value = builder.alloca(return_value_type, name="return")

            for i in range(len(returns)):
                ptr = builder.gep(return_value, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)])
                if self.children[i].type.is_numeric():
                    builder.store(mask_number_to_its_type(builder, returns[i], ptr.type.pointee), ptr)
                elif self.children[i].type.is_string():
                    # XXX: the bitcast is needed since we can put a smaller array into a bigger one
                    builder.store(returns[i], builder.bitcast(ptr, ir.PointerType(returns[i].type)))
                else:
                    builder.store(returns[i], ptr)

            builder.ret(builder.load(return_value))


ReturnStat.llvm_codegen = return_stat_llvm_codegen


def stat_list_llvm_codegen(self, variable_state):
    for statement in self.children:
        statement.llvm_codegen(variable_state)
        global STOP_FLAG
        if STOP_FLAG:
            STOP_FLAG = False
            return


StatList.llvm_codegen = stat_list_llvm_codegen


def functiondef_llvm_codegen(self, variable_state):
    parameters_type = [convert_type_to_llvm_type(x.type) for x in self.parameters]

    # dictionary containing a mapping from symbol to parameter index
    # used to resolve lambda lifted symbols to their pointers
    nested_symbols = {}
    lambda_lifted_symbols = get_lambda_lifting(self.symbol, self.body.symtab)
    for lambda_lifted_symbol in lambda_lifted_symbols:
        parameters_type += [ir.PointerType(convert_type_to_llvm_type(lambda_lifted_symbol.type))]
        nested_symbols[lambda_lifted_symbol] = len(parameters_type) - 1

    match len(self.returns):
        case 0:
            if self.parent is None:  # main
                return_type = ir.IntType(32)
            else:
                return_type = ir.VoidType()

        case 1:
            return_type = get_llvm_type_for_return(self.returns[0].type)

        case _:  # multiple return values, use a struct
            return_types = [get_llvm_type_for_return(x.type) for x in self.returns]
            return_type = ir.LiteralStructType(return_types)

    func_type = ir.FunctionType(return_type, tuple(parameters_type))

    func = ir.Function(module, func_type, name=self.symbol.name)
    block = func.append_basic_block(name="entry")
    func.nested_symbols = nested_symbols

    builder.position_at_start(block)

    for symbol in self.body.symtab:  # TODO: do we have to initialize variables?
        if symbol.type.size == 0:
            continue
        elif symbol.function_symbol != self.symbol:
            continue
        elif 'assignable' not in symbol.type.qualifiers and not symbol.is_array():
            continue
        else:
            pointer = builder.alloca(convert_type_to_llvm_type(symbol.type), name=symbol.name)
            variable_state[symbol] = pointer

    for i in range(len(self.parameters)):
        builder.store(func.args[i], variable_state[self.parameters[i]])

    return_to = builder.block

    for function in self.body.defs.children:  # codegen children functions
        function.llvm_codegen(variable_state)

    builder.position_at_end(return_to)

    self.body.body.llvm_codegen(variable_state)

    if self.parent is None:  # main
        builder.ret(ir.Constant(ir.IntType(32), 0))
    else:
        if not builder.block.is_terminated:  # XXX: could happen
            if return_type == ir.VoidType():
                builder.ret_void()
            else:
                raise RuntimeError(f"At least one path of the function '{self.symbol.name}' doesn't end with a return, even if one is needed")


FunctionDef.llvm_codegen = functiondef_llvm_codegen


def llvm_codegen(ast):
    global module, builder
    module = ir.Module()
    builder = ir.IRBuilder()

    add_extern_functions(module)

    variable_state = {}
    ast.llvm_codegen(variable_state)

    return module
