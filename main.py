#!/usr/bin/env python3

"""The main function of the compiler, AKA the compiler driver"""

import lexer
import parser
from support import *
from datalayout import *
from cfg import *
from regalloc import *
from codegen import *


def compile_program(text):
    print("\n\nPARSING\n\n")
    lex = lexer.Lexer(text)
    pars = parser.Parser(lex)
    program = pars.program()
    print('\n', program, '\n')

    print("\n\nSTATEMENTS\n\n")
    program.navigate(print_stat_list)

    print("\n\nNODE LIST\n\n")
    node_list = get_node_list(program)
    for n in node_list:
        print(type(n), id(n), '->', type(n.parent), id(n.parent))
    print('\nTotal nodes in IR:', len(node_list), '\n')

    print("\n\nLOWERING\n\n")
    program.navigate(lowering)

    print("\n\nFLATTENING\n\n")
    program.navigate(flattening)
    print('\n', program, '\n')

    print("\n\nMAKING DOTTY\n\n")
    print_dotty(program, "log.dot")
    print("\nA dot file representation of the program is in the log.dot file\n")

    print("\n\nMEMORY-TO-REGISTER PROMOTION\n\n")
    perform_memory_to_register_promotion(program)

    print("\n\nDATALAYOUT\n\n")
    perform_data_layout(program)
    print('\n', program, '\n')

    print("\n\nBUILDING THE CONTROL FLOW GRAPH\n\n")
    cfg = CFG(program)

    print("\n\nLIVENESS ANALYSIS\n\n")
    cfg.liveness()
    cfg.print_liveness()

    print("\n\nRETURN ANALYSIS\n\n")
    cfg.return_analysis()
    print("\nAll procedures that need to return parameters correctly return them\n")

    cfg.print_cfg_to_dot("cfg.dot")

    print("\nA dot file representation of the program is in the cfg.dot file\n")

    print("\n\nREGISTER ALLOCATION\n\n")
    ra = LinearScanRegisterAllocator(cfg, 11)
    reg_alloc = ra()
    print(ra)
    print("\n\n")
    print(reg_alloc)

    print("\n\nCODE GENERATION\n\n")
    code = generate_code(program, reg_alloc)
    print(code)

    return code

def driver_main():
    from sys import argv

    # compile the test program specified in the Lexer
    test_program=lexer.__test_program

    # get a test program from the arguments
    if len(argv) > 2:
        with open(argv[1], 'r') as inf :
            test_program = inf.read()

    code = compile_program(test_program)

    # write the code in the file specifed in the arguments
    if len(argv) >= 2:
        with open(argv[-1], 'w') as outf :
            outf.write(code)


if __name__ == '__main__':
    driver_main()
