from tests.utils import run_test, check_expected_output


class TestCalls():

    def test_simple_procedure_with_arguments(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/procedure_calls/calls/00.simple_procedure_with_arguments/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/procedure_calls/calls/00.simple_procedure_with_arguments/expected")

    def test_multiple_procedures_with_arguments(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/procedure_calls/calls/01.multiple_procedures_with_arguments/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/procedure_calls/calls/01.multiple_procedures_with_arguments/expected")

    def test_procedures_with_arguments_with_for(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/procedure_calls/calls/02.procedures_with_arguments_with_for/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/procedure_calls/calls/02.procedures_with_arguments_with_for/expected")

    def test_changed_datalayout(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/procedure_calls/calls/03.changed_datalayout/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/procedure_calls/calls/03.changed_datalayout/expected")
