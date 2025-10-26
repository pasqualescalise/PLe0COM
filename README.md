# PLe0COM

Optimizing (toy) compiler for a modified and extended version of the [PL/0 language](https://en.wikipedia.org/wiki/PL/0)

This is a fork of pl0com, a toy compiler for the [Code Optimization and Transformation course held at Politecnico di Milano](https://cto-course-polimi.github.io/)

It features a hand-written recursive-descent parser, an AST and an IR, various optimization stages and a code generation stage which produces (hopefully) valid 32 bit ARMv6 code

I'm using it to experiment and have fun with compiler stuff

## Extended features

+ Functions can accept parameters and can return values; callers can ignore return values
+ Support for ints, shorts, bytes, booleans and strings (char arrays)
+ Explicit logging: it's clear what the compiler does and why (with colors!)
+ More ControlFlowGraph analysis
+ Optimizations
	+ Function inlining
	+ Dead code elimination
	+ Memory-to-register promotion
	+ Chain Load-Store elimination
	+ Loop Unrolling
+ Fully working test suite written using [pytest](https://docs.pytest.org/en/stable/index.html)
+ PEP8 compliant (except E501)
+ ARM ABI compliant (circa, since we can return multiple values)
+ An AST interpreter
+ LLVM integration using [llvmlite](https://pypi.org/project/llvmlite/)

## Dependencies

The code generated should work on CPU that supports ARMv6, like any Raspberry PI

### On non-ARM Linux machines

```sh
sudo apt install qemu-user gcc-arm-linux-gnueabi
```

### On ARM Linux machines

```sh
sudo apt install gcc
```

To use the Makefile on ARM, the variables `$(CC)` and `$(RUN_COMMAND)` must be changed

### Python version

The code was tested on Python 3.11 and uses features from version 3.10 (e.g. `match`),
so any version 3.10+ should work

### LLVM

For LLVM, this project uses [llvmlite](https://pypi.org/project/llvmlite/), please [follow their instructions to install it](https://llvmlite.readthedocs.io/en/latest/admin-guide/install.html)

### Test suite

The only dependency is [pytest](https://docs.pytest.org/en/stable/index.html), [follow their instruction to install it](https://docs.pytest.org/en/stable/getting-started.html#get-started)

## Compile and run

### Compile

You can run the compiler with

```sh
python3 main.py -i <input_file> [-o <output_file> (default: out.s) -O{0,1,2} (default: 2)]
```

to generate an ARMv6 assembly file

To compile and assemble, just use

```sh
make compile input=<input_file> [EXECUTABLE=<executable> (default: out) OPTIMIZATION_LEVEL={0,1,2} (default: 2)]
```

### Execute

To run the binary on a non-ARM Linux machine, then use

```sh
make execute [EXECUTABLE=<executable> (default: out) OPTIMIZATION_LEVEL={0,1,2} (default: 2)]
```

### Compile and Execute

Or just do both with

```sh
make input=<input_file> [EXECUTABLE=<executable> (default: out) OPTIMIZATION_LEVEL={0,1,2} (default: 2)]
```

### Debugger

To debug the executable on a non-ARM machine, use

```sh
make input=<input_file> dbg=True [EXECUTABLE=<executable> (default: out) OPTIMIZATION_LEVEL={0,1,2} (default: 2)]
```

and in another terminal

```sh
make dbg
```

The debugger can be set in the Makefile or using the variable `$(DEBUGGER)`; I use [pwndbg](https://github.com/pwndbg/pwndbg/), if you want standard gdb on a non-ARM machine use gdb-multiarch

### Interpreter

You can run the Abstract Syntax Tree Intepreter with

```sh
python3 main.py -I -i <input_file> [-o <output_file> (default: out.s) -O{0,1,2} (default: 2)]
```

or with make

```sh
make input=<input_file> interpret=True [OPTIMIZATION_LEVEL={0,1,2} (default: 2)]
```

### LLVM

You can run the LLVM compiler with

```sh
python3 main.py -L -i <input_file> [-o <output_file> (default: out.s) -O{0,1,2} (default: 2)]
```

or with make

```sh
make input=<input_file> llvm=True [OPTIMIZATION_LEVEL={0,1,2} (default: 2)]
```

## Testing

All tests are located in the "tests" directory, organized in subdirectories and classes. Each tests has its own corresponding expected output/expected error message.

You can know more about tests by looking in the "tests" directory or by executing `python3 tests/test.py`

### Single test

```sh
python3 tests/test.py -t <test_name> [-I (to use the interpreter) -L (to use LLVM) -O{0,1,2} (default: 2)]
```

### Single class

```sh
python3 tests/test.py -c <class_name> [-I (to use the interpreter) -L (to use LLVM) -O{0,1,2} (default: 2)]
```

### Single directory

```sh
python3 tests/test.py -d <directory_path> [-I (to use the interpreter) -L (to use LLVM) -O{0,1,2} (default: 2)] 
```

### All tests at once with a specific optimization level and compiler/interpreter

Either

```sh
python3 tests/test.py -a [-I (to use the interpreter) -L (to use LLVM) -O{0,1,2} (default: 2)] 
```

or

```sh
make -s testall [interpret=True (to use the interpreter) llvm=True (to use LLVM) OPTIMIZATION_LEVEL={0,1,2} (default: 2)]
```

compiles and executes all tests, checking if their output is the expected one

### All possible tests

Either

```sh
python3 tests/test.py -A
```

or

```sh
make -s testallall
```

compiles and executes all tests with all possible combination of optimization level and compiler/interpreter, checking if their output is the expected one
