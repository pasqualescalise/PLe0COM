from tests.utils import get_test_output, check_expected_output


class TestWhileConstruct():

    def test_while(self, optimization_level, interpreter, debug_executable):
        output = get_test_output("tests/basic_constructs/while_construct/00.while/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/basic_constructs/while_construct/00.while/expected")
