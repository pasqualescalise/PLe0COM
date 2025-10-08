from tests.utils import get_test_output, check_expected_output


class TestNestedProceduresAndAccess():

    def test_local_variables_of_deeply_nested_procedures(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/00.local_variables_of_deeply_nested_procedures/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/00.local_variables_of_deeply_nested_procedures/expected")

    def test_reading_and_writing_local_variables_of_deeply_nested_procedures(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/01.reading_and_writing_local_variables_of_deeply_nested_procedures/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/01.reading_and_writing_local_variables_of_deeply_nested_procedures/expected")

    def test_nested_procedures_with_arguments(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/02.nested_procedures_with_arguments/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/02.nested_procedures_with_arguments/expected")

    def test_multiple_nested_procedure_with_arguments(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/03.multiple_nested_procedure_with_arguments/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/03.multiple_nested_procedure_with_arguments/expected")

    def test_nested_sibling_procedures(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/04.nested_sibling_procedures/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/04.nested_sibling_procedures/expected")

    def test_multiple_nested_procedures_with_arguments_with_for_and_scope(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/05.multiple_nested_procedures_with_arguments_with_for_and_scope/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/05.multiple_nested_procedures_with_arguments_with_for_and_scope/expected")

    def test_nested_grandparent_procedures(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/06.nested_grandparent_procedures/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/06.nested_grandparent_procedures/expected")

    def test_nesting_accessing_main_procedures(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/07.nesting_accessing_main_procedures/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/07.nesting_accessing_main_procedures/expected")

    def test_optimized_power_procedure(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/08.optimized_power_procedure/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/08.optimized_power_procedure/expected")

    def test_nested_returns(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/09.nested_returns/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/09.nested_returns/expected")

    def test_nested_returns_with_different_parameters_and_returns(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/10.nested_returns_with_different_parameters_and_returns/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/10.nested_returns_with_different_parameters_and_returns/expected")

    def test_optimized_power_procedure_with_returns(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/11.optimized_power_procedure_with_returns/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/11.optimized_power_procedure_with_returns/expected")

    def test_optimized_power_procedure_with_local_variables_and_nested_procedures(self, optimization_level, interpreter):
        output = get_test_output("tests/procedure_calls/nested_procedures_and_access/12.optimized_power_procedure_with_local_variables_and_nested_procedures/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/procedure_calls/nested_procedures_and_access/12.optimized_power_procedure_with_local_variables_and_nested_procedures/expected")
