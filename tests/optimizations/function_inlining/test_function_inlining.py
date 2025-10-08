from tests.utils import get_test_output, check_expected_output


# TODO: check that functions actually get inlined

class TestFunctionInlining():

    def test_function_inlining(self, optimization_level, interpreter):
        output = get_test_output("tests/optimizations/function_inlining/00.function_inlining/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/optimizations/function_inlining/00.function_inlining/expected")

    def test_inline_functions_in_main(self, optimization_level, interpreter):
        output = get_test_output("tests/optimizations/function_inlining/01.inline_functions_in_main/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/optimizations/function_inlining/01.inline_functions_in_main/expected")

    def test_remove_inlined_functions(self, optimization_level, interpreter):
        output = get_test_output("tests/optimizations/function_inlining/02.remove_inlined_functions/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/optimizations/function_inlining/02.remove_inlined_functions/expected")
