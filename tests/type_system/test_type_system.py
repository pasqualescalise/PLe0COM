from tests.utils import run_test, check_expected_output


class TestTypeSystem():

    def test_int_types_and_arrays(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/00.int_types_and_arrays/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/00.int_types_and_arrays/expected")

    def test_short_char_unsigned(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/01.short_char_unsigned/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/01.short_char_unsigned/expected")

    def test_strings(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/02.strings/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/02.strings/expected")

    def test_booleans(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/03.booleans/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/03.booleans/expected")

    def test_boolean_operations(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/04.boolean_operations/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/04.boolean_operations/expected")

    def test_numeric_with_functions(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/05.numeric_with_functions/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/05.numeric_with_functions/expected")

    def test_numeric_arrays_with_functions(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/06.numeric_arrays_with_functions/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/06.numeric_arrays_with_functions/expected")

    def test_boolean_strings_with_functions(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/07.boolean_strings_with_functions/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/07.boolean_strings_with_functions/expected")

    def test_array_assignments(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/08.array_assignments/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/08.array_assignments/expected")

    def test_more_complex_array_assignments(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/type_system/09.more_complex_array_assignments/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/type_system/09.more_complex_array_assignments/expected")
