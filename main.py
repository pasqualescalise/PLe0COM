#!/usr/bin/env python3

"""The main function of the compiler, AKA the compiler driver"""

from argparse import ArgumentParser
from os.path import join, exists
from copy import deepcopy

from frontend.lexer import Lexer
from frontend.parser import Parser
from frontend.abstract_syntax_tree_optimizations import perform_abstract_syntax_tree_optimizations
from frontend.type_checking import perform_type_checking
from frontend.interpreter import perform_interpretation

from ir.support import get_node_list, lowering, flattening
from ir.intermediate_representation_optimizations import perform_intermediate_representation_optimizations
from ir.function_tree import FunctionTree

from llvm.llvm_codegen import llvm_codegen

from cfg.cfg import ControlFlowGraph
from cfg.control_flow_graph_optimizations import perform_control_flow_graph_optimizations
from cfg.control_flow_graph_analyses import perform_control_flow_graph_analyses

from backend.datalayout import perform_data_layout
from backend.regalloc import LinearScanRegisterAllocator
from backend.codegen import generate_code
from backend.post_code_generation_optimizations import perform_post_code_generation_optimizations

from logger import initialize_logger, h1, h2, remove_formatting, green, yellow, cyan, bold, italic


# These can be specified from the command line to get the corresponding
# debug information printed to file
debug_info_choices = ["pre_opts_ast", "ast_ftree", "loop_unrolling", "post_opts_ast", "interpreter_output", "pre_opts_ir", "memory_to_register_promotion", "function_inlining", "post_opts_ir", "dead_variable_elimination", "chain_load_store_elimination", "post_cfg_ir", "cfg", "cfg_dot", "ftree", "pre_opts_code", "code"]


# Returns a dictionary with all the debug informations, like the AST,
# the IR, the FunctionTree, the CFG, the actual code, etc.
def compile_program(text, optimization_level, interpret, llvm):
    debug_info = {}

    print(h1("FRONT-END"))

    print(h2("PARSING"))
    lex = Lexer(text)
    pars = Parser(lex)
    program = pars.program()
    print(f"\n{green('Abstract Syntax Tree:')}\n{program}")
    debug_info["pre_opts_ast"] = deepcopy(program)

    main_symbol = pars.current_function

    print(h2("FUNCTION TREE"))
    FunctionTree.populate_function_tree(program, main_symbol)
    debug_info["ast_ftree"] = FunctionTree.root

    # XXX: SOME OPTIMIZATIONS GO HERE
    print(h2("ABSTRACT SYNTAX TREE OPTIMIZATIONS"))
    perform_abstract_syntax_tree_optimizations(program, optimization_level, debug_info)

    print(f"\n{green('Optimized Abstract Syntax Tree:')}\n{program}")

    print(h2("TYPE CHECKING"))
    perform_type_checking(program)

    print(f"\n{green('Typed Abstract Syntax Tree:')}\n{program}")
    debug_info["post_opts_ast"] = deepcopy(program)

    print(h2("NODE LIST"))
    node_list = get_node_list(program, quiet=True)
    for node in node_list:
        if node.parent is not None:
            print(f"{yellow(f'{node.type_repr()}, {id(node)}')} is child of {yellow(f'{node.parent.type_repr()}, {id(node.parent)}')}")
        else:
            print(f"{yellow(f'{node.type_repr()}, {id(node)}')} is {bold('root')} node")
    print(f"\nTotal nodes in IR: {cyan(len(node_list))}")

    print(h2("STATEMENT LISTS"))
    for node in node_list:
        try:
            print(f"{bold(node.get_content())}")
        except AttributeError:
            pass  # not a StatList

    if interpret:
        print(h2("INTERPRETER"))
        interpreter_output = perform_interpretation(program)
        print(interpreter_output)
        debug_info["interpreter_output"] = interpreter_output
        return debug_info

    if llvm:
        print(h2("LLVM"))
        llvm_code = llvm_codegen(program)
        print(llvm_code)
        debug_info["code"] = llvm_code
        return debug_info

    ##############################################

    print(h1("MIDDLE-END"))

    print(h2("LOWERING"))
    FunctionTree.navigate(lowering, quiet=False)

    print(h2("FLATTENING"))
    FunctionTree.navigate(flattening, quiet=False)

    print(f"\n{green('Intermediate Representation:')}\n{program}")
    debug_info["pre_opts_ir"] = deepcopy(program)

    # XXX: OTHER OPTIMIZATIONS GO HERE
    print(h2("INTERMEDIATE REPRESENTATION OPTIMIZATIONS"))
    perform_intermediate_representation_optimizations(program, optimization_level, debug_info)

    print(f"\n{green('Optimized program:')}\n{program}")
    debug_info["post_opts_ir"] = deepcopy(program)

    ##############################################

    print(h1("CONTROL FLOW GRAPH ANALYSES"))
    cfg = ControlFlowGraph(program)

    perform_control_flow_graph_analyses(cfg)

    # XXX: AND OTHER OPTIMIZATIONS GO HERE
    print(h2("CONTROL FLOW GRAPH OPTIMIZATIONS"))
    cfg = perform_control_flow_graph_optimizations(program, cfg, optimization_level, debug_info)

    print(f"\n{green('Optimized program:')}\n{program}")
    debug_info["post_cfg_ir"] = deepcopy(program)

    debug_info['cfg'] = cfg
    debug_info['cfg_dot'] = cfg.cfg_to_dot()

    print(h2("NEW FUNCTION TREE"))
    FunctionTree.populate_function_tree(program, main_symbol)
    print(FunctionTree.root)
    debug_info["ftree"] = FunctionTree.root

    ##############################################

    print(h1("BACK-END"))

    print(h2("DATALAYOUT"))
    print(italic("Allocating variables on the stack frame or in the global section\n"))
    perform_data_layout(program)
    print(f"\n{green('Program after datalayout:')}\n{program}")

    print(h2("REGISTER ALLOCATION"))
    register_allocator = LinearScanRegisterAllocator(cfg, 11)
    register_allocation = register_allocator()
    print(register_allocator.get_liveness_intervals())
    print(register_allocation)

    print(h2("CODE GENERATION"))
    code = generate_code(program, register_allocation)
    printable_code = '\n'.join([repr(x) for x in code]) + '\n'
    print(f"\n{green('Final compiled code: ')}\n\n{printable_code}")
    debug_info["pre_opts_code"] = deepcopy(code)

    # XXX: THE LAST OPTIMIZATIONS GO HERE
    print(h2("POST-CODE-GENERATION OPTIMIZATIONS"))
    code = perform_post_code_generation_optimizations(code, optimization_level)
    printable_code = '\n'.join([repr(x) for x in code]) + '\n'
    print(f"\n{green('Final optimized code: ')}\n\n{printable_code}")
    debug_info["code"] = code

    return debug_info


def put_debug_info_in_file(debug_info, print_debug, debug_directory):
    if len(print_debug) == 0:
        return

    if not exists(debug_directory):
        raise RuntimeError(f"Debug directory {debug_directory} does not exist! Please create it before asking for debug information")

    for info in print_debug:
        if info not in debug_info:
            continue

        filename = f"{join(debug_directory, info)}.debug"
        output = remove_formatting(repr(debug_info[info]))
        match info:
            case "interpreter_output":
                output = debug_info[info]

            case "loop_unrolling" | "memory_to_register_promotion" | "function_inlining" | "dead_variable_elimination" | "chain_load_store_elimination" | "cfg":
                # print list using newlines
                output = remove_formatting('\n'.join([repr(x) for x in debug_info[info]]))

            case "cfg_dot":
                filename = f"{join(debug_directory, 'cfg')}.dot"
                output = remove_formatting(debug_info[info])

            case "pre_opts_code" | "code":
                output = remove_formatting('\n'.join([repr(x) for x in debug_info[info]]) + '\n')
                filename = f"{join(debug_directory, info)}.s"

        with open(f"{filename}", 'w') as debugf:
            debugf.write(output)


def driver_main():
    parser = ArgumentParser(prog="Pl0COM", description="Optimizing compiler for the (modified) PL/0 language", epilog="")

    parser.add_argument('-i', '--input_file', required="True")
    parser.add_argument('-o', '--output_file', default="out.s", help="Compilation: assembly output")
    parser.add_argument('-O', '--optimization_level', default="2", choices=["0", "1", "2"])
    parser.add_argument('-I', '--interpret', default=False, action='store_true')
    parser.add_argument('-L', '--llvm', default=False, action='store_true')
    parser.add_argument('-p', '--print_debug', default="", choices=debug_info_choices, nargs='+', help="What debug info to print to a file in the debug directory")
    parser.add_argument('-d', '--debug_directory', default="./debug")

    args = parser.parse_args()

    # get a test program from the arguments
    with open(args.input_file, 'r') as inf:
        test_program = inf.read()

    debug_info = compile_program(test_program, int(args.optimization_level), args.interpret, args.llvm)
    put_debug_info_in_file(debug_info, args.print_debug, args.debug_directory)

    if not args.interpret:
        with open(args.output_file, 'w') as outf:
            if args.llvm:
                printable_code = repr(debug_info["code"])
            else:
                printable_code = '\n'.join([repr(x) for x in debug_info["code"]]) + '\n'
            outf.write(remove_formatting(printable_code))

        print(green(bold(f"\nThe code can be found in the '{args.output_file}' file")))


if __name__ == '__main__':
    initialize_logger()
    driver_main()
