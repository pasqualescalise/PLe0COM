import pytest


def pytest_addoption(parser):
    parser.addoption('-O', '--optimization_level', choices=["0", "1", "2"], default=["2"], help="Optimization Level")
    parser.addoption('-I', '--interpreter', default=[False], action='store_const', const=[True], help="Interpret the AST instead of compiling")
    parser.addoption('-D', '--debug_executable', default=[False], action='store_const', const=[True], help="Execute the program using a debugger")


def pytest_generate_tests(metafunc):
    if "optimization_level" in metafunc.fixturenames:
        metafunc.parametrize("optimization_level", metafunc.config.getoption("optimization_level"))
    if "interpreter" in metafunc.fixturenames:
        metafunc.parametrize("interpreter", metafunc.config.getoption("interpreter"))
    if "debug_executable" in metafunc.fixturenames:
        metafunc.parametrize("debug_executable", metafunc.config.getoption("debug_executable"))


def pytest_configure(config):
    config.addinivalue_line("markers", "not_optimization_level_zero: can't run test at -O0")
    config.addinivalue_line("markers", "not_optimization_level_one: can't run test at -O1")
    config.addinivalue_line("markers", "not_optimization_level_two: can't run test at -O2")

    config.addinivalue_line("markers", "not_interpreter: can't run test on interpreter")
    config.addinivalue_line("markers", "not_compiler: can't run test on compiler")  # XXX: this is useless


# Add markers allowing tests to be skipped based on optimization level and if they are
# being interpreted or compiled
def pytest_collection_modifyitems(config, items):
    optimization_level = int(config.getoption("--optimization_level"))

    if optimization_level == 0:
        skip_if_optimization_level_zero = pytest.mark.skip(reason="optimization level must not be 0")
        for item in items:
            if "not_optimization_level_zero" in item.keywords:
                item.add_marker(skip_if_optimization_level_zero)
    elif optimization_level == 1:
        skip_if_optimization_level_one = pytest.mark.skip(reason="optimization level must not be 1")
        for item in items:
            if "not_optimization_level_one" in item.keywords:
                item.add_marker(skip_if_optimization_level_one)
    elif optimization_level == 2:
        skip_if_optimization_level_two = pytest.mark.skip(reason="optimization level must not be 2")
        for item in items:
            if "not_optimization_level_two" in item.keywords:
                item.add_marker(skip_if_optimization_level_two)

    interpreter = config.getoption("--interpreter")[0]

    if interpreter:
        skip_if_interpreter = pytest.mark.skip(reason="can't run test on interpreter")
        for item in items:
            if "not_interpreter" in item.keywords:
                item.add_marker(skip_if_interpreter)
    else:
        skip_if_compiler = pytest.mark.skip(reason="can't run test on compiler")
        for item in items:
            if "not_compiler" in item.keywords:
                item.add_marker(skip_if_compiler)
