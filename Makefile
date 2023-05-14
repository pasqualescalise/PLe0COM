tests:= $(wildcard ./tests/*.pl0)
tests_expected_directory := "./tests/expected"
output_directory := "./tests/output"
executables := $(wildcard ./out*)

all: compile test

compile:
	python3 main.py $(test) out.s

test:
	echo "\nRUNNING\n";\
	arm-linux-gnueabi-gcc out.s runtime.c -g -static -march=armv6 -o out;\
	if [ $(gdb) ]; then\
		qemu-arm -cpu arm1136 -g 7777 out;\
	else\
		qemu-arm -cpu arm1136 out;\
	fi;

testall:
	output_directory="$(output_directory)";\
	tests="$(tests)";\
	tests_expected_directory="$(tests_expected_directory)";\
	if [ ! -d $$output_directory ]; then\
		mkdir $$output_directory;\
	else\
		rm $$output_directory/*;\
	fi;\
	for test in $$tests; do\
		basename=$$(basename "$$test" .pl0).output;\
		$(MAKE) compile test="$$test" > /dev/null 2> $$output_directory/$$basename;\
		return_value=$$(echo $$?);\
		if [ "$$return_value" -eq "0" ]; then\
			$(MAKE) test | sed -n -e "4,\$$p" > $$output_directory/$$basename;\
		fi;\
	done;\
	for output in $$output_directory/*.output; do\
		basename=$$(basename "$$output" .output);\
		expected=$$tests_expected_directory/$$(basename "$$output" .output).expected;\
		if [ ! -f $$expected ]; then\
			printf "\e[31mExpected output does not exist for test $$basename\e[0m\n";\
			continue;\
		fi;\
		if output=$$(diff -y -W 72 $$output $$expected); then\
				printf "\e[32mTest $$basename passed!\e[0m\n";\
		else\
				printf "\e[31mTest $$basename not passed\e[0m\n";\
		fi;\
	done;

clean:
	rm out.s out

gdb:
	gdb-multiarch --eval-command="file out" --eval-command="target remote :7777" --eval-command="b __pl0_start" --eval-command="c"

showpdf:
	dot -Tpdf cfg.dot -o cfg.pdf;\
	zathura cfg.pdf &

showpng:
	dot -Tpng cfg.dot -o cfg.png;\
	feh cfg.png &

.PHONY: compile test clean gdb showpdf showpng
