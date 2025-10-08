import pytest

from tests.utils import compile, get_test_output, check_expected_output


class TestReturns():

    def test_simple_return_statement(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/returns/00.simple_return_statement/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/returns/00.simple_return_statement/expected")

    def test_multiple_returned_values(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/returns/01.multiple_returned_values/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/returns/01.multiple_returned_values/expected")

    def test_last_instruction_optimization(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/returns/02.last_instruction_optimization/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/returns/02.last_instruction_optimization/expected")

    @pytest.mark.not_interpreter
    def test_procedure_that_doesnt_return(self, optimization_level, interpreter):
        with pytest.raises(RuntimeError) as e:
            compile("tests/procedure_calls/returns/03.procedure_that_doesnt_return/code.pl0", int(optimization_level), interpreter, "")

        check_expected_output(f"{str(e.value)}\n", "tests/procedure_calls/returns/03.procedure_that_doesnt_return/expected_error")

    def test_more_complex_returns(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/returns/04.more_complex_returns/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/returns/04.more_complex_returns/expected")
