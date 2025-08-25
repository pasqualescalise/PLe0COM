#include <stdio.h>

/* Use a C compiler to assemble and link a compiled program with the runtime:
 *   cc runtime.c out.s -o out
 * where out.s is the assembly output of the PL/0 compiler, and cc is a
 * C compiler targeting ARM. */


extern void __pl0_start(void);


void __pl0_print_integer(int param)
{
  printf("%d\n", param);
}


void __pl0_print_short(short param)
{
  printf("%hd\n", param);
}


void __pl0_print_byte(char param)
{
  printf("%hhd\n", param);
}


void __pl0_print_unsigned_short(unsigned short param)
{
  printf("%hu\n", param);
}


void __pl0_print_unsigned_byte(unsigned char param)
{
  printf("%hhu\n", param);
}


void __pl0_print_string(int param)
{
  printf("%s\n", param);
}


void __pl0_print_boolean(int param)
{
  if (param) {
  	printf("%s\n", "True");
  } else {
  	printf("%s\n", "False");
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
