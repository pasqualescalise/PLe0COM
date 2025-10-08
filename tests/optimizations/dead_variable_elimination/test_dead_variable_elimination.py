from tests.utils import get_test_output, check_expected_output


class TestDeadVariableElimination():

    def test_dead_variable_elimination(self, optimization_level, interpreter):
        output = get_test_output("tests/optimizations/dead_variable_elimination/00.dead_variable_elimination/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/optimizations/dead_variable_elimination/00.dead_variable_elimination/expected")
