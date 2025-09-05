#include <stdio.h>

/* Use a C compiler to assemble and link a compiled program with the runtime:
 *   cc runtime.c out.s -o out
 * where out.s is the assembly output of the PL/0 compiler, and cc is a
 * C compiler targeting ARM. */


extern void __pl0_start(void);


void __pl0_print_integer(int param, int newline)
{
  if (newline) {
  	printf("%d\n", param);
  } else {
  	printf("%d", param);
  }
}


void __pl0_print_short(short param, int newline)
{
  if (newline) {
  	printf("%hd\n", param);
  } else {
  	printf("%hd", param);
  }
}


void __pl0_print_byte(char param, int newline)
{
  if (newline) {
  	printf("%hhd\n", param);
  } else {
  	printf("%hhd", param);
  }
}


void __pl0_print_unsigned_short(unsigned short param, int newline)
{
  if (newline) {
  	printf("%hu\n", param);
  } else {
  	printf("%hu", param);
  }
}


void __pl0_print_unsigned_byte(unsigned char param, int newline)
{
  if (newline) {
  	printf("%hhu\n", param);
  } else {
  	printf("%hhu", param);
  }
}


void __pl0_print_string(int param, int newline)
{
  if (newline) {
  	printf("%s\n", param);
  } else {
  	printf("%s", param);
  }
}


void __pl0_print_boolean(int param, int newline)
{
  if (param) {
    if (newline) {
  	  printf("%s\n", "True");
	} else {
  	  printf("%s", "True");
	}
  } else {
    if (newline) {
  	  printf("%s\n", "False");
	} else {
  	  printf("%s", "False");
	}
  }
}


int __pl0_read(void)
{
  int tmp;
  scanf("%d", &tmp);
  return tmp;
}


int main(int argc, char *argv[])
{
  __pl0_start();
}
