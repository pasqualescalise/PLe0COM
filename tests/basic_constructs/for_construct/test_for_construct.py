from tests.utils import run_test, check_expected_output


class TestForConstruct():

    def test_simple_for(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/basic_constructs/for_construct/00.simple_for/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/basic_constructs/for_construct/00.simple_for/expected")

    def test_simple_nested_for(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/basic_constructs/for_construct/01.simple_nested_for/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/basic_constructs/for_construct/01.simple_nested_for/expected")

    def test_multiple_nested_fors(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/basic_constructs/for_construct/02.multiple_nested_for/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/basic_constructs/for_construct/02.multiple_nested_for/expected")

    def test_descending_and_ascending_loops(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/basic_constructs/for_construct/03.descending_and_ascending_loops/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/basic_constructs/for_construct/03.descending_and_ascending_loops/expected")
