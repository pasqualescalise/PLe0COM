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

        assert len(debug_info['function_inlining']) == 11

        # check that all functions are inlined into 'function_not_to_inline' except it
        for info in debug_info['function_inlining']:
            if info[0].symbol.name == "function_not_to_inline":
                assert info[1] == "Too many instructions"
            else:
                assert info[1].name == "function_not_to_inline"

    def test_inline_functions_in_main(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/optimizations/function_inlining/01.inline_functions_in_main/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/optimizations/function_inlining/01.inline_functions_in_main/expected")

        # check that the inlining is actually inlining
        check_expected_output(repr(debug_info['ast_ftree']), "tests/optimizations/function_inlining/01.inline_functions_in_main/ast_ftree.expected")
        check_expected_output(repr(debug_info['ftree']), "tests/optimizations/function_inlining/01.inline_functions_in_main/ftree.expected")

        assert len(debug_info['function_inlining']) == 10

        # check that all functions are inlined into main
        for info in debug_info['function_inlining']:
            assert info[1].name == "main"

    def test_remove_inlined_functions(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/optimizations/function_inlining/02.remove_inlined_functions/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/optimizations/function_inlining/02.remove_inlined_functions/expected")

        # check that the inlining is actually inlining
        check_expected_output(repr(debug_info['ast_ftree']), "tests/optimizations/function_inlining/02.remove_inlined_functions/ast_ftree.expected")
        check_expected_output(repr(debug_info['ftree']), "tests/optimizations/function_inlining/02.remove_inlined_functions/ftree.expected")

        assert len(debug_info['function_inlining']) == 4

        assert debug_info['function_inlining'][0][0].symbol.name == "not_inline_2"
        assert debug_info['function_inlining'][0][1] == "Too many instructions"

        assert debug_info['function_inlining'][1][0].symbol.name == "inline_2"
        assert debug_info['function_inlining'][1][1].name == "inline_1"

        assert debug_info['function_inlining'][2][0].symbol.name == "inline_1"
        assert debug_info['function_inlining'][2][1].name == "not_inline_1"

        assert debug_info['function_inlining'][3][0].symbol.name == "not_inline_1"
        assert debug_info['function_inlining'][3][1] == "Too many instructions"
