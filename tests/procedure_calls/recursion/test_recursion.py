from tests.utils import run_test, check_expected_output


class TestRecursion():

    def test_recursive_function(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/procedure_calls/recursion/00.recursive_function/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/procedure_calls/recursion/00.recursive_function/expected")

    def test_recursive_nested_function(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/procedure_calls/recursion/01.recursive_nested_function/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/procedure_calls/recursion/01.recursive_nested_function/expected")
