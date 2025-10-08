import pytest

from tests.utils import compile, get_test_output, check_expected_output


class TestChainLoadStoreElimination():

    def test_chain_load_store_elimination(self, optimization_level, interpreter):
        output = get_test_output("tests/optimizations/chain_load_store_elimination/00.chain_load_store_elimination/code.pl0", int(optimization_level), interpreter)
        check_expected_output(output, "tests/optimizations/chain_load_store_elimination/00.chain_load_store_elimination/expected")

    @pytest.mark.not_optimization_level_zero
    @pytest.mark.not_optimization_level_one
    @pytest.mark.not_interpreter
    def test_useless_function(self, optimization_level, interpreter):
        with pytest.raises(RuntimeError) as e:
            compile("tests/optimizations/chain_load_store_elimination/01.useless_function/code.pl0", int(optimization_level), interpreter, "")

        check_expected_output(f"{str(e.value)}\n", "tests/optimizations/chain_load_store_elimination/01.useless_function/expected")
