#!/usr/bin/env python3

"""
Testing platform
"""

import pytest

from argparse import ArgumentParser


default_args = ["--show-capture=no", "--no-header", "--tb=line"]


def single_test(test, optimization_level, interpret, llvm, quiet, debug):
    args = ["-v"]

    args += [] if quiet else ["-s"]
    args += [f"--optimization_level={optimization_level}"]
    args += ["-I"] if interpret else []
    args += ["-L"] if llvm else []
    args += ["-D"] if debug else []

    args += ["-k", test]

    retvalue = pytest.main(args)
    print(f"Return value: {retvalue}")


def single_category(category, optimization_level, interpret, llvm):
    args = default_args[:]

    args += [f"--optimization_level={optimization_level}"]
    args += ["-I"] if interpret else []
    args += ["-L"] if llvm else []

    args += ["-k", category]

    pytest.main(args)


def single_directory(directory, optimization_level, interpret, llvm):
    args = default_args[:]

    args += [f"--optimization_level={optimization_level}"]
    args += ["-I"] if interpret else []
    args += ["-L"] if llvm else []

    args += [directory]

    pytest.main(args)


def test_all(optimization_level, interpret, llvm):
    args = default_args[:]

    args += [f"--optimization_level={optimization_level}"]
    args += ["-I"] if interpret else []
    args += ["-L"] if llvm else []

    pytest.main(args)


def test_all_all():
    args = default_args[:]

    for optimization_level in ["0", "1", "2"]:
        print(f"Optimization level {optimization_level}, compiling")
        pytest.main(args + [f"--optimization_level={optimization_level}"])

    for optimization_level in ["0", "1", "2"]:
        print(f"Optimization level {optimization_level}, interpreting")
        pytest.main(args + [f"--optimization_level={optimization_level}", "-I"])

    for optimization_level in ["0", "1", "2"]:
        print(f"Optimization level {optimization_level}, compiling with llvm")
        pytest.main(args + [f"--optimization_level={optimization_level}", "-L"])


def main():
    parser = ArgumentParser(prog="Pl0COM tester", description="Tester for the optimizing compiler for the (modified) PL/0 language", epilog="")

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument('-t', '--test', help="Test a single file (can omit the 'test_' prefix)")
    group.add_argument('-c', '--category', help="Test a single class (can omit the 'Test' prefix)")
    group.add_argument('-d', '--directory', help="Test all tests in a directory (path can be relative to the project root)")
    group.add_argument('-a', '--all', default=False, action='store_true', help="Test all tests with a specific optimization level and either compiler or interpreter")
    group.add_argument('-A', '--all_all', default=False, action='store_true', help="Test all tests with all possible optimization levels and both compiler and interpreter")

    parser.add_argument('-O', '--optimization_level', default="2", choices=["0", "1", "2"])
    parser.add_argument('-I', '--interpret', default=False, action='store_true')
    parser.add_argument('-L', '--llvm', default=False, action='store_true')
    parser.add_argument('-q', '--quiet', default=False, action='store_true', help="Only considered if testing a single test (-t), otherwise automatically set to true")
    parser.add_argument('-D', '--debug', default=False, action='store_true', help="Only considered if testing a single test (-t), otherwise automatically set to false: execute the program using a debugger")

    args = parser.parse_args()

    if args.interpret:
        action = 'interpreting'
    elif args.llvm:
        action = 'compiling with llvm'
    else:
        action = 'compiling'

    if args.test is not None:
        print(f"TESTING {args.test}")
        print(f"Optimization level {args.optimization_level}, {action}")
        single_test(args.test, args.optimization_level, args.interpret, args.llvm, args.quiet, args.debug)
        return

    if args.category is not None:
        print(f"TESTING CATEGORY {args.category}")
        print(f"Optimization level {args.optimization_level}, {action}")
        single_category(args.category, args.optimization_level, args.interpret, args.llvm)
        return

    if args.directory is not None:
        print(f"TESTING DIRECTORY {args.directory}")
        print(f"Optimization level {args.optimization_level}, {action}")
        single_directory(args.directory, args.optimization_level, args.interpret, args.llvm)
        return

    elif args.all:
        print("TESTING ALL")
        print(f"Optimization level {args.optimization_level}, {action}")
        test_all(args.optimization_level, args.interpret, args.llvm)
        return

    print("FULL TESTING")
    test_all_all()


if __name__ == "__main__":
    main()
