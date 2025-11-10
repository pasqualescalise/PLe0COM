import pytest

from tests.utils import run_test, check_expected_output

from frontend.abstract_syntax_tree_optimizations.loop_unrolling import LOOP_UNROLLING_FACTOR


@pytest.mark.not_optimization_level_zero
@pytest.mark.not_optimization_level_one
class TestLoopUnrolling():

    def test_loop_unrolling(self, optimization_level, interpreter, debug_executable):
        output, debug_info = run_test("tests/optimizations/loop_unrolling/00.loop_unrolling/code.pl0", int(optimization_level), interpreter, debug_executable)
        check_expected_output(output, "tests/optimizations/loop_unrolling/00.loop_unrolling/expected")

        # check that the loop is actually unrolled
        assert len(debug_info['loop_unrolling']) == 1

        pre_opts_for = debug_info['loop_unrolling'][0][0]
        post_opts_for = debug_info['loop_unrolling'][0][1]

        assert pre_opts_for.epilogue is None
        assert post_opts_for.epilogue is not None

        # the unrolled body is (body + step (1 statement)) * LOOP_UNROLLING_FACTOR - 1 (the "normal" step)
        assert len(post_opts_for.body.children) == (len(pre_opts_for.body.children) + 1) * LOOP_UNROLLING_FACTOR - 1
