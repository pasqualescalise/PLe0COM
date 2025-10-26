import pytest

from tests.utils import run_test, check_expected_output


@pytest.mark.not_optimization_level_zero
@pytest.mark.not_optimization_level_one
@pytest.mark.not_interpreter
@pytest.mark.not_llvm
class TestFunctionInlining():

    def test_function_inlining(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/optimizations/function_inlining/00.function_inlining/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/optimizations/function_inlining/00.function_inlining/expected")

        # check that the inlining is actually inlining
        check_expected_output(repr(debug_info['ast_ftree']), "tests/optimizations/function_inlining/00.function_inlining/ast_ftree.expected")
        check_expected_output(repr(debug_info['ftree']), "tests/optimizations/function_inlining/00.function_inlining/ftree.expected")

    def test_inline_functions_in_main(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/optimizations/function_inlining/01.inline_functions_in_main/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/optimizations/function_inlining/01.inline_functions_in_main/expected")

        # check that the inlining is actually inlining
        check_expected_output(repr(debug_info['ast_ftree']), "tests/optimizations/function_inlining/01.inline_functions_in_main/ast_ftree.expected")
        check_expected_output(repr(debug_info['ftree']), "tests/optimizations/function_inlining/01.inline_functions_in_main/ftree.expected")

    def test_remove_inlined_functions(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/optimizations/function_inlining/02.remove_inlined_functions/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/optimizations/function_inlining/02.remove_inlined_functions/expected")

        # check that the inlining is actually inlining
        check_expected_output(repr(debug_info['ast_ftree']), "tests/optimizations/function_inlining/02.remove_inlined_functions/ast_ftree.expected")
        check_expected_output(repr(debug_info['ftree']), "tests/optimizations/function_inlining/02.remove_inlined_functions/ftree.expected")
