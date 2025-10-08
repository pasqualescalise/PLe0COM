from subprocess import run
from tempfile import NamedTemporaryFile

from main import compile_program
from logger import initialize_logger


# Returns the assembly code produced by the compiler or raises an Error
def compile(in_file, optimization_level, interpreted, out_file):
    with open(in_file, 'r') as inf:
        test_program = inf.read()

    initialize_logger()

    try:
        code = compile_program(test_program, optimization_level, interpreted, out_file)
    except Exception as e:
        print(f"Raised Exception {repr(e)}")
        raise e

    return code


# Assemble and execute the compiled code, return the stdout of the asembled program
def execute(out_file, executable_file):
    assemble_command = f"arm-linux-gnueabi-gcc -g -static -march=armv6 -z noexecstack {out_file.name} runtime.c -o {executable_file.name}"
    run(assemble_command.split(' '))

    execute_command = f"qemu-arm -cpu arm1136 {executable_file.name}"
    execute = run(execute_command.split(' '), capture_output=True)

    output = execute.stdout.decode('utf-8')

    return output


# Returns the output of the compiled/interpreted test, also prints it
def get_test_output(in_file, optimization_level, interpreted):
    out_temp_file = NamedTemporaryFile(mode="w+", suffix=".s")
    executable_temp_file = NamedTemporaryFile(mode="w+")

    code = compile(in_file, optimization_level, interpreted, out_temp_file.name)

    out_temp_file.write(code)
    out_temp_file.seek(0)

    if interpreted:
        output = out_temp_file.read()
    else:
        output = execute(out_temp_file, executable_temp_file)

    out_temp_file.close()
    executable_temp_file.close()

    print("\n\033[36mOUTPUT\033[0m\n")
    print(output)

    return output


# Check that the given output is equal as the content of the expected_file
def check_expected_output(output, expected_file):
    with open(expected_file, 'r') as exp:
        expected = exp.read()

    assert output == expected
