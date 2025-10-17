from tests.utils import get_test_output, check_expected_output


class TestArithmetic():

    def test_division(self, optimization_level, interpreter, debug_executable):
        output = get_test_output("tests/arithmetic/00.division/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/arithmetic/00.division/expected")

    def test_modulus(self, optimization_level, interpreter, debug_executable):
        output = get_test_output("tests/arithmetic/01.modulus/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/arithmetic/01.modulus/expected")

    def test_increment(self, optimization_level, interpreter, debug_executable):
        output = get_test_output("tests/arithmetic/02.increment/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/arithmetic/02.increment/expected")
