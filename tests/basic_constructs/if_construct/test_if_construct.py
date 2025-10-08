from tests.utils import get_test_output, check_expected_output


class TestIfConstruct():

    def test_simple_if_else(self, optimization_level, interpreter):
        output = get_test_output("tests/basic_constructs/if_construct/00.simple_if_else/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/basic_constructs/if_construct/00.simple_if_else/expected")

    def test_if_elif_else(self, optimization_level, interpreter):
        output = get_test_output("tests/basic_constructs/if_construct/01.simple_if_elif_else/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/basic_constructs/if_construct/01.simple_if_elif_else/expected")

    def test_switch_with_if_else(self, optimization_level, interpreter):
        output = get_test_output("tests/basic_constructs/if_construct/02.switch_with_if_else/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/basic_constructs/if_construct/02.switch_with_if_else/expected")
