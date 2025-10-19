import pytest

from tests.utils import run_test, check_expected_output

from ir.ir import LoadImmInstruction


@pytest.mark.not_optimization_level_zero
@pytest.mark.not_optimization_level_one
@pytest.mark.not_interpreter
class TestDeadVariableElimination():

    def test_dead_variable_elimination(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/optimizations/dead_variable_elimination/00.dead_variable_elimination/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/optimizations/dead_variable_elimination/00.dead_variable_elimination/expected")

        # check that we have removed the right dead variable
        assert len(debug_info['dead_variable_elimination']) == 1

        eliminated_instruction = debug_info['dead_variable_elimination'][0]

        assert isinstance(eliminated_instruction, LoadImmInstruction)
        assert eliminated_instruction.val == 2
