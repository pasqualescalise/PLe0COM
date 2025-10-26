SHELL := /bin/bash
STDOUT := /dev/stdout

CC := arm-linux-gnueabi-gcc
CFLAGS := -g -static -march=armv6 -z noexecstack

LLVM_IR := out.ll
ASSEMBLY := out.s
EXECUTABLE := out
OPTIMIZATION_LEVEL := 2
RUN_COMMAND := qemu-arm -cpu arm1136 
DEBUGGER := pwndbg

TEST_FILE := tests/test.py
TEST_COMMAND := python3 

CFG_DOT_FILE := debug/cfg.dot
CFG_PDF_FILE := debug/cfg.pdf
CFG_PNG_FILE := debug/cfg.png

INTERPRET := $(interpret)
LLVM := $(llvm)

all: call

call:
ifndef INTERPRET
ifndef LLVM
	$(MAKE) compile
	$(MAKE) execute
else
	$(MAKE) compile-llvm
	$(MAKE) execute
endif
else
	$(MAKE) interpret
endif

compile:
	if [ $(input) ]; then\
		python3 main.py -i $(input) -o $(ASSEMBLY) -O$(OPTIMIZATION_LEVEL);\
	else\
		printf "\n\e[31mPlease specify input file\e[0m\n";\
	fi;
	$(CC) $(CFLAGS) $(ASSEMBLY) runtime.c -o $(EXECUTABLE)
	if [ ! $$? -eq 0 ]; then\
		printf "\n\e[31mThe program didn't compile successfully\e[0m\n";\
	fi;

execute:
	printf "\n\e[36mRUNNING\e[0m\n\n";
	if [ $(dbg) ]; then\
		$(RUN_COMMAND) -g 7777 $(EXECUTABLE);\
	else\
		$(RUN_COMMAND) $(EXECUTABLE);\
	fi;

interpret:
	if [ $(input) ]; then\
		python3 main.py -i $(input) -o $(STDOUT) -O$(OPTIMIZATION_LEVEL) -I;\
		if [ ! $$? -eq 0 ]; then\
			printf "\n\e[31mThe program didn't interpret successfully\e[0m\n";\
			exit 1;\
		fi;\
	else\
		printf "\n\e[31mPlease specify input file\e[0m\n";\
	fi;

compile-llvm:
	python3 main.py -i $(input) -o $(LLVM_IR) -O$(OPTIMIZATION_LEVEL) -L;\
	llc --march arm $(LLVM_IR) -o $(ASSEMBLY);\
	if [ ! $$? -eq 0 ]; then\
		printf "\n\e[31mThe program didn't llvm compile successfully\e[0m\n";\
		exit 1;\
	fi;\
	$(CC) $(CFLAGS) $(ASSEMBLY) runtime.c -o $(EXECUTABLE);\
	if [ ! $$? -eq 0 ]; then\
		printf "\n\e[31mThe program didn't compile successfully\e[0m\n";\
		exit 1;\
	fi;

testall:
ifndef INTERPRET
ifndef LLVM
	$(TEST_COMMAND) $(TEST_FILE) -a -O$(OPTIMIZATION_LEVEL)
else
	$(TEST_COMMAND) $(TEST_FILE) -a -O$(OPTIMIZATION_LEVEL) -L
endif
else
	$(TEST_COMMAND) $(TEST_FILE) -a -O$(OPTIMIZATION_LEVEL) -I
endif

testallall:
	$(TEST_COMMAND) $(TEST_FILE) -A

clean:
	rm $(ASSEMBLY) $(EXECUTABLE) $(CFG_DOT_FILE) $(CFG_PDF_FILE) $(CFG_PNG_FILE)

dbg:
	$(DEBUGGER) --eval-command="file $(EXECUTABLE)" --eval-command="target remote :7777" --eval-command="b main" --eval-command="c"

showpdf:
	dot -Tpdf $(CFG_DOT_FILE) -o $(CFG_PDF_FILE)
	xdg-open $(CFG_PDF_FILE) &

showpng:
	dot -Tpng $(CFG_DOT_FILE) -o $(CFG_PNG_FILE)
	xdg-open $(CFG_PNG_FILE) &

profile:
	$(MAKE) compile test=$(test);
	time $(RUN_COMMAND) $(EXECUTABLE);

.PHONY: compile test clean dbg showpdf showpng
