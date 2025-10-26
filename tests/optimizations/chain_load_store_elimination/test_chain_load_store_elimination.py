import pytest

from tests.utils import compile, run_test, check_expected_output

from ir.ir import LoadInstruction


@pytest.mark.not_optimization_level_zero
@pytest.mark.not_optimization_level_one
@pytest.mark.not_interpreter
@pytest.mark.not_llvm
class TestChainLoadStoreElimination():

    def test_chain_load_store_elimination(self, optimization_level, interpreter, llvm, debug_executable):
        output, debug_info = run_test("tests/optimizations/chain_load_store_elimination/00.chain_load_store_elimination/code.pl0", int(optimization_level), interpreter, llvm, debug_executable)
        check_expected_output(output, "tests/optimizations/chain_load_store_elimination/00.chain_load_store_elimination/expected")

        # check that the inlining is actually inlining
        check_expected_output(repr(debug_info['ast_ftree']), "tests/optimizations/chain_load_store_elimination/00.chain_load_store_elimination/ast_ftree.expected")
        check_expected_output(repr(debug_info['ftree']), "tests/optimizations/chain_load_store_elimination/00.chain_load_store_elimination/ftree.expected")

        # check that the correct instructions are being eliminated
        eliminated_instructions = debug_info['chain_load_store_elimination']
        assert len(eliminated_instructions) == 2

        assert isinstance(eliminated_instructions[0], LoadInstruction)
        assert isinstance(eliminated_instructions[1], LoadInstruction)

    def test_useless_function(self, optimization_level, interpreter, llvm, debug_executable):
        with pytest.raises(RuntimeError) as e:
            compile("tests/optimizations/chain_load_store_elimination/01.useless_function/code.pl0", int(optimization_level), interpreter, llvm)

        check_expected_output(f"{str(e.value)}\n", "tests/optimizations/chain_load_store_elimination/01.useless_function/expected_error")
