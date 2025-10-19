from tests.utils import run_test, check_expected_output


class TestLexer():

    def test_lexer_keywords(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/lexer/00.lexer_keywords/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/lexer/00.lexer_keywords/expected")

    def test_keyword_strings(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/lexer/01.keyword_strings/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/lexer/01.keyword_strings/expected")
