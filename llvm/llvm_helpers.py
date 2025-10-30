#!/usr/bin/env python3

"""Helper functions used by the LLVM code generator"""

from llvmlite import ir

from ir.ir import ArrayType, TYPENAMES


def convert_type_to_llvm_type(type):
    match type:
        case x if x == TYPENAMES['int'] or x == TYPENAMES['uint']:  # no distinction
            return ir.IntType(32)
        case x if x == TYPENAMES['short'] or x == TYPENAMES['ushort']:  # TODO: distinction?
            return ir.IntType(16)
        case x if x == TYPENAMES['byte'] or x == TYPENAMES['ubyte']:  # TODO: distinction?
            return ir.IntType(8)
        case x if x == TYPENAMES['boolean']:
            return ir.IntType(1)
        case x if x == TYPENAMES['char']:
            return ir.IntType(8)
        case ArrayType():
            llvm_type = convert_type_to_llvm_type(type.basetype)
            for dim in list(reversed(type.dims)):
                llvm_type = ir.ArrayType(llvm_type, dim)
            return llvm_type
        case None:
            return ir.VoidType()
        case _:
            raise NotImplementedError


# Truncate or extend number types to match the asked type
def mask_number_to_its_type(builder, value, type):
    if value.type == type:
        return value
    elif value.type.width > type.width:
        return builder.trunc(value, type)
    else:
        return builder.zext(value, type)


# Return the symbols that need to be lambda lifted (passed as
# parameters when calling "function_symbol" from a node that
# has "symtab" as SymbolTable)
def get_lambda_lifting(function_symbol, symtab):
    lambda_lifted = []

    for symbol in symtab:
        if symbol.type.size == 0:
            continue
        elif symbol.function_symbol != function_symbol:
            if not symbol.used_in_nested_procedure:
                continue
            lambda_lifted += [symbol]

    return lambda_lifted


# Get a symbol reference from variable_state, respecting lambda lifting
def get_symbol_reference(builder, symbol, variable_state):
    symbol_reference = variable_state[symbol]
    if symbol_reference.function != builder.function:
        # the symbol is from a different function and has been passed via parameters
        index = builder.function.nested_symbols[symbol]
        symbol_reference = builder.function.args[index]

    return symbol_reference


# We need to define as extern all the functions defined in runtime.c
def add_extern_functions(module):
    void = ir.VoidType()

    parameters_type = (ir.IntType(32), ir.IntType(32))
    func_type = ir.FunctionType(void, parameters_type)
    ir.Function(module, func_type, name="__pl0_print_integer")

    parameters_type = (ir.IntType(16), ir.IntType(32))
    func_type = ir.FunctionType(void, parameters_type)
    ir.Function(module, func_type, name="__pl0_print_short")
    ir.Function(module, func_type, name="__pl0_print_unsigned_short")

    parameters_type = (ir.IntType(8), ir.IntType(32))
    func_type = ir.FunctionType(void, parameters_type)
    ir.Function(module, func_type, name="__pl0_print_byte")
    ir.Function(module, func_type, name="__pl0_print_unsigned_byte")

    parameters_type = (ir.IntType(32), ir.IntType(32))
    func_type = ir.FunctionType(void, parameters_type)
    ir.Function(module, func_type, name="__pl0_print_string")

    parameters_type = (ir.IntType(32), ir.IntType(32))
    func_type = ir.FunctionType(void, parameters_type)
    ir.Function(module, func_type, name="__pl0_print_boolean")

    func_type = ir.FunctionType(ir.IntType(32), ())
    ir.Function(module, func_type, name="__pl0_read")
