#!/usr/bin/env python3

"""The main function of the compiler, AKA the compiler driver"""

import lexer
import parser
from support import get_node_list, flattening, lowering
from datalayout import perform_data_layout, perform_memory_to_register_promotion
from cfg import ControlFlowGraph
from regalloc import LinearScanRegisterAllocator
from codegen import generate_code
from logger import initialize_logger, h1, h2, remove_formatting, red, green, yellow, cyan, bold, italic, underline
# from optimizations import loop_unrolling


def compile_program(text):
    print(h1("FRONT-END"))

    print(h2("PARSING"))
    lex = lexer.Lexer(text)
    pars = parser.Parser(lex)
    program = pars.program()
    print(f"\n{green('Parsed program:')}\n{program}")

    print(h2("NODE LIST"))
    node_list = get_node_list(program, quiet=True)
    for node in node_list:
        if node.parent is not None:
            print(f"{yellow(f'{node.type()}, {id(node)}')} is child of {yellow(f'{node.parent.type()}, {id(node.parent)}')}")
        else:
            print(f"{yellow(f'{node.type()}, {id(node)}')} is {bold('root')} node")
    print(f"\nTotal nodes in IR: {cyan(len(node_list))}")

    print(h2("STATEMENT LISTS"))
    for node in node_list:
        try:
            print(f"{bold(node.get_content())}")
        except AttributeError:
            pass  # not a StatList

    ##############################################

    print(h1("MIDDLE-END"))

    # XXX: SOME OPTIMIZATIONS GO HERE
    # print(h2("LOOP UNROLLING"))
    # loop_unrolling(program)
    # program.navigate(loop_unrolling, quiet=True)
    # print('\n', program, '\n')

    print(h2("LOWERING"))
    program.navigate(lowering, quiet=False)

    print(h2("FLATTENING"))
    program.navigate(flattening, quiet=False)

    print(f"\n{green('Lowered and flattened program:')}\n{program}")

    # XXX: OTHER OPTIMIZATIONS GO HERE
    print(h2("MEMORY-TO-REGISTER PROMOTION"))
    perform_memory_to_register_promotion(program)

    ##############################################

    print(h1("CONTROL FLOW GRAPH ANALYSIS"))
    cfg = ControlFlowGraph(program)

    print(h2("LIVENESS ANALYSIS"))
    cfg.liveness()
    print(cfg.liveness_analysis_representation())

    # XXX: AND OTHER OPTIMIZATIONS GO HERE
    print(h2("RETURN ANALYSIS"))
    cfg.return_analysis()

    cfg.print_cfg_to_dot("cfg.dot")
    print(f"\n{underline('A dot file representation of the ControlFlowGraph can be found in the cfg.dot file')}\n")

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
    print(f"\n{green('Final compiled code: ')}\n\n{code}")

    return remove_formatting(code)


def driver_main():
    from sys import argv

    if len(argv) <= 2:
        print(red(bold("\nPlease supply a test file in the pl0 language as first argument")))
        exit(1)

    # get a test program from the arguments
    if len(argv) > 2:
        with open(argv[1], 'r') as inf:
            test_program = inf.read()

    code = compile_program(test_program)

    # write the code in the file specifed in the arguments
    if len(argv) >= 2:
        with open(argv[-1], 'w') as outf:
            outf.write(code)

        print(green(bold(f"\nThe code can be found in the '{argv[-1]}' file")))


if __name__ == '__main__':
    initialize_logger()
    driver_main()
