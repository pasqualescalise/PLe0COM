SHELL := /bin/bash
STDOUT := /dev/stdout

AS := arm-linux-gnueabi-as
ASFLAGS := -g -march=armv6
LD := arm-linux-gnueabi-ld
LDFLAGS :=

ASSEMBLY := out.s
OBJECT := out.o
EXECUTABLE := out
STDLIB = $(wildcard stdlib/*.s)
OPTIMIZATION_LEVEL := 2
RUN_COMMAND := qemu-arm -cpu arm1136 
DEBUGGER := pwndbg

TEST_FILE := tests/test.py
TEST_COMMAND := python3 

CFG_DOT_FILE := debug/cfg.dot
CFG_PDF_FILE := debug/cfg.pdf
CFG_PNG_FILE := debug/cfg.png

INTERPRET := $(interpret)

all: call

call:
ifndef INTERPRET
	$(MAKE) compile
	$(MAKE) execute
else
	$(MAKE) interpret
endif

compile:
	if [ $(input) ]; then\
		python3 main.py -i $(input) -o $(ASSEMBLY) -O$(OPTIMIZATION_LEVEL);\
	else\
		printf "\n\e[31mPlease specify input file\e[0m\n";\
	fi;
	$(AS) $(ASFLAGS) $(ASSEMBLY) $(STDLIB) -o $(OBJECT);\
	$(LD) -o $(EXECUTABLE) $(OBJECT);\
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

testall:
ifndef INTERPRET
	$(TEST_COMMAND) $(TEST_FILE) -a -O$(OPTIMIZATION_LEVEL)
else
	$(TEST_COMMAND) $(TEST_FILE) -a -O$(OPTIMIZATION_LEVEL) -I
endif

testallall:
	$(TEST_COMMAND) $(TEST_FILE) -A

clean:
	rm $(ASSEMBLY) $(OBJECT) $(EXECUTABLE) $(CFG_DOT_FILE) $(CFG_PDF_FILE) $(CFG_PNG_FILE)

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
