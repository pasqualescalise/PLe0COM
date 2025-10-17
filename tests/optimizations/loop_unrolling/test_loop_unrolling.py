from tests.utils import get_test_output, check_expected_output


# TODO: check that loop actually get unrolled

class TestLoopUnrolling():

    def test_loop_unrolling(self, optimization_level, interpreter, debug_executable):
        output = get_test_output("tests/optimizations/loop_unrolling/00.loop_unrolling/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/optimizations/loop_unrolling/00.loop_unrolling/expected")
