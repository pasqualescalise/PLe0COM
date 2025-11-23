from glob import glob
from subprocess import run
from tempfile import NamedTemporaryFile

from main import compile_program
from logger import initialize_logger, remove_formatting


# Returns the assembly code produced by the compiler or raises an Error
def compile(in_file, optimization_level, interpreted):
    with open(in_file, 'r') as inf:
        test_program = inf.read()

    initialize_logger()

    try:
        debug_info = compile_program(test_program, optimization_level, interpreted)
    except Exception as e:
        print(f"Raised Exception {repr(e)}")
        raise e

    return debug_info


# Assemble, link and execute the compiled code, return the stdout of the asembled program
def execute(out_file, object_file, executable_file, debug):
    assemble_bin = "arm-linux-gnueabi-as"
    assemble_flags = "-g -march=armv6"
    stdlib_files = ' '.join(glob("stdlib/*.s"))
    assemble_command = f"{assemble_bin} {assemble_flags} {out_file.name} {stdlib_files} -o {object_file.name}"
    run(assemble_command.split(' '))

    linker_bin = "arm-linux-gnueabi-ld"
    linker_command = f"{linker_bin} {object_file.name} -o {executable_file.name}"
    run(linker_command.split(' '))

    execute_command = f"qemu-arm -cpu arm1136 {executable_file.name}"
    if debug:  # open gdb port 7777
        execute_command = f"qemu-arm -cpu arm1136 -g 7777 {executable_file.name}"
        print(f"Start a debugger in another terminal with `make -s dbg EXECUTABLE=\"{executable_file.name}\"")
    execute = run(execute_command.split(' '), capture_output=True)

    output = execute.stdout.decode('utf-8')
    return output


# Returns and prints the output of the compiled/interpreted test + the debug information
def run_test(in_file, optimization_level, interpreted, debug):
    debug_info = compile(in_file, optimization_level, interpreted)

    if interpreted:
        output = debug_info['interpreter_output']
    else:
        out_temp_file = NamedTemporaryFile(mode="w+", suffix=".s")
        executable_temp_file = NamedTemporaryFile(mode="w+")
        object_temp_file = NamedTemporaryFile(mode="w+")

        code = debug_info['code']
        printable_code = '\n'.join([repr(x) for x in code]) + '\n'

        out_temp_file.write(remove_formatting(printable_code))
        out_temp_file.seek(0)

        output = execute(out_temp_file, object_temp_file, executable_temp_file, debug)

        out_temp_file.close()
        object_temp_file.close()
        executable_temp_file.close()

        print("\n\033[36mOUTPUT\033[0m\n")
        print(output)

    return output, debug_info


# Check that the given output is equal as the content of the expected_file
def check_expected_output(output, expected_file):
    with open(expected_file, 'r') as exp:
        expected = exp.read()

    assert remove_formatting(output) == expected
