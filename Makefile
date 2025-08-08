SHELL := /bin/bash

CC := arm-linux-gnueabi-gcc
CFLAGS := -g -static -march=armv6 -z noexecstack

ASSEMBLY := out.s
EXECUTABLE := out
OPTIMIZATION_LEVEL := 2
RUN_COMMAND := qemu-arm -cpu arm1136 
DEBUGGER := pwndbg

TESTS_SRC_DIR:= "./tests"
TESTS_EXP_DIR := "./tests/expected"
TESTS_OUT_DIR := "./tests/output"

CFG_DOT_FILE := cfg.dot
CFG_PDF_FILE := cfg.pdf
CFG_PNG_FILE := cfg.png

all: compile execute

compile:
	if [ $(test) ]; then\
		python3 main.py -i $(test) -o $(ASSEMBLY) -O$(OPTIMIZATION_LEVEL);\
	fi;
	$(CC) $(CFLAGS) $(ASSEMBLY) runtime.c -o $(EXECUTABLE)
	if [ ! $$? -eq 0 ]; then\
		printf "\n\e[31mThe program didn't compile successfully\e[0m\n";\
	fi;

execute:
	printf "\n\e[36mRUNNING\e[0m\n\n";
	if [ $(dbg) ]; then\
		$(RUN_COMMAND) -g 7777 $(EXECUTABLE);\
	elif [ $(test) ]; then\
		test_name=$$(basename "$(test)" .pl0);\
		output_file=$(TESTS_OUT_DIR)/single_test.output;\
		$(RUN_COMMAND) $(EXECUTABLE) > $$output_file;\
		cat $$output_file;\
		$(MAKE) -s check_output test_name=$$test_name output_file=$$output_file;\
	else\
		$(RUN_COMMAND) $(EXECUTABLE);\
	fi;

testall:
	if [ ! -d $(TESTS_OUT_DIR) ]; then\
		mkdir $(TESTS_OUT_DIR);\
	else\
		rm -f $(TESTS_OUT_DIR)/*;\
	fi;
	for test_file in $(TESTS_SRC_DIR)/*.pl0; do\
		test_name=$$(basename "$$test_file" .pl0);\
		output_file=$(TESTS_OUT_DIR)/"$$test_name".output;\
		$(MAKE) compile test="$$test_file" > /dev/null 2> $$output_file;\
		return_value=$$(echo $$?);\
		if [ "$$return_value" -eq "0" ]; then\
			$(MAKE) execute | sed -n -e "4,\$$p" > $$output_file;\
		else\
			sed -i -e "\$$d" $$output_file;\
			sed -n -i -e "\$$p" $$output_file;\
		fi;\
		$(MAKE) -s check_output test_name=$$test_name output_file=$$output_file;\
	done;

check_output:
	expected_file=$(TESTS_EXP_DIR)/"$(test_name)".expected;\
	if [ ! -f $$expected_file ]; then\
		printf "\e[31mExpected output does not exist for test $(test_name)\e[0m\n";\
	elif output=$$(diff -y -W 72 $(output_file) $$expected_file); then\
		printf "\e[32mTest $(test_name) passed!\e[0m\n";\
	else\
		printf "\e[31mTest $(test_name) not passed\e[0m\n";\
	fi;

clean:
	rm $(ASSEMBLY) $(EXECUTABLE) $(CFG_DOT_FILE) $(CFG_PDF_FILE) $(CFG_PNG_FILE)

dbg:
	$(DEBUGGER) --eval-command="file $(EXECUTABLE)" --eval-command="target remote :7777" --eval-command="b __pl0_start" --eval-command="c"

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
