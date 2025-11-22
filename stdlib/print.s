.data
overflow: .ascii "-2147483648"
true_no_newline: .ascii "True"
false_no_newline: .ascii "False"
true_newline: .ascii "True\n"
false_newline: .ascii "False\n"

.text
.arch armv6
.syntax unified

.include "stdlib/macros.s"


.global __pl0_print_numeric

@ Write the number given to r0 to stdout, converting it to string;
@ numbers can be 10 digits long max
@
@ Hugely inspired by <https://armasm.com/docs/arithmetic/itoa/>
@
@ Registers:     
@  r4:  address of the next place to write to
@  r5:  number to write
@  r6:  current 10^x
@  r7:  current power (x from above) 
@  r8:  loop counter
@  r9:  size of the buffer allocated on the stack
@  r10: if lsb is 1, print a newline; if second lsb is 1, the given number is negative
@
@ Parameters:
@  r0: number to process
@  r1: either 0 or 1, wheter to add a newline at the end or not
@ 
@ Returns:
@  nothing
__pl0_print_numeric: 
	push    {r4, r5, r6, r7, r8, r9, r10, r11, lr}
	mov     r11, sp

	mov     r5, r0              @ load number to process
	mov     r10, r1             @ if we need to print a newline, set the r10 lsb to 1
	mov     r7, #9              @ max size is 10
	mov     r8, #0              @ init loop counter 

	cmp     r5, #0
	bge     special_case_zero

	cmp     r5, #2147483648     @ special case: if we want to print the biggest number,
	beq     write_overflow      @ 0x80000000, just print it directly

	orr     r10, #2             @ if the number is negative, turn it to positive
	sub     r5, r5, #1          @ and set the r10 second lsb to 1
	mvn     r5, r5

@ if the number is 0, we don't need to calculate the power, we can write it directly
special_case_zero:
	cmp     r5, #0
	bne     find_start
	b       write_zero

@ find first power of ten to use
find_start:
	pow     #10, r7             @ get cur power of ten 
	mov     r6, r0              @ move pow result to r6 
	cmp     r6, r5              @ compare 10^x to number to print 
	ble     allocate_outs       @ if less than number, continue
	sub     r7, #1              @ if still bigger than num to print, 
	                            @ decrement pow and try again 
	b       find_start   

@ allocate on the stack a buffer big enough for the number 
allocate_outs:
	add     r9, r7, #1          @ we always need to add one since the power is one less than the
	                            @ number of digits we need

	cmp     r10, #2             @ add one also if we need to print the minus
	blt     align_outs
	add     r9, r9, #1

@ in order to keep the stack aligned, make sure to always multiply by a multiple of 4
align_outs:
	add     r12, r9, #4
	and     r12, r12, #3        @ r12 is r9 % 4

	push    {r10}               @ spill r10 to use it for this calculation
	mov     r10, #4
	sub     r12, r10, r12
	pop     {r10}

	add     r9, r9, r12

	sub sp, sp, r9              @ do the actual stack allocation
	mov r4, sp

	cmp r10, #2
	blt find_digit
	mov r12, #'-'               @ add the minus if needed
	strb r12, [r4], #1

@ process number and print 
find_digit:
	cmp     r5, r6              @ compare remaining number to 10^x 
	blt     store_digit         @ if less than, store digit 
	add     r8, r8, #1          @ increment counter 
	sub     r5, r5, r6          @ subtract 10^x from remaining and go again 
	b       find_digit 

store_digit:
	add     r8, #'0'            @ add counter to ASCII zero to get ASCII number 
	strb    r8, [r4], #1        @ store in the buffer and increment 

	@ prepare next loop 
	sub     r7, #1              @ subtract one from the counter
	cmp     r7, #0              @ compare exp to 0 
	blt     exit                @ if exp is < zero, leave loop 
	pow     #10, r7             @ get next power of ten 
	mov     r6, r0              @ move 10^x into r6 
	mov     r8, #0              @ reset loop counter 
	b       find_digit 

exit: 
	and     r12, r10, #1
	cmp     r12, #0
	beq     write_numeric
	mov     r8, #'\n'           @ add the newline if we need to
	strb    r8, [r4], #1

write_numeric:
	mov     r1, sp              @ the buffer is at the top of the stack
	sub     r2, r4, sp          @ the length of the buffer is r4 - sp
	write_to_stdout r1, r2
	b return_numeric

write_zero:
	sub     sp, sp, #4
	mov     r4, sp

	mov     r12, #'0'
	strb    r12, [r4], #1

	cmp     r10, #0
	beq     write_numeric
	mov     r9, #'\n'           @ add the newline if we need to
	strb    r9, [r4], #1
	b       write_numeric

write_overflow:
	sub     sp, sp, #12
	mov     r4, sp
	ldr     r12, =overflow

	loop_numeric:
	cmp     r8, #11
	bge     newline

	ldrb    r9, [r12], #1
	strb    r9, [r4], #1

	add     r8, r8, #1
	b       loop_numeric

	newline:                    @ TODO: test printing overflow without newline
	cmp     r10, #0
	beq     write_numeric
	mov     r9, #'\n'           @ add the newline if we need to
	strb    r9, [r4], #1
	b       write_numeric

return_numeric:
	mov sp, r11
	pop {r4, r5, r6, r7, r8, r9, r10, r11, lr}
	bx lr



.global __pl0_print_string

@ Write the string given to r0 to stdout
@
@ Registers:     
@  r8:  loop counter, counts the size of the string to print
@
@ Parameters:
@  r0: string to print
@  r1: either 0 or 1, wheter to add a newline at the end or not
@ 
@ Returns:
@  nothing
__pl0_print_string: 
	push    {r8, r11, lr}
	mov     r11, sp

	mov     r8, #0

@ count up until we find a 0x0 byte, then we know the string is finished
loop_string:
	add     r12, r0, r8
	ldrb    r12, [r12]
	cmp     r12, #0
	beq     write_string
	add     r8, #1
	b       loop_string

write_string:
	write_to_stdout r0, r8      @ actually write the string

	cmp     r1, #0
	beq     return_string

	mov     r12, #'\n'          @ if we need to print a newline, put it on the stack
	push    {r12}               @ then write it
	mov     r12, sp             @ TODO: this uses two different writes, we should
	mov     r8, #1              @       really buffer them
	write_to_stdout r12, r8

return_string:
	mov     sp, r11
	pop     {r8, r11, lr}
	bx      lr



.global __pl0_print_boolean

@ Write the boolean given to r0 to stdout, converting it to string
@
@ Parameters:
@  r0: boolean to print
@  r1: either 0 or 1, wheter to add a newline at the end or not
@ 
@ Returns:
@  nothing
__pl0_print_boolean: 
	push    {r11, lr}
	mov     r11, sp

	cmp     r0, #0
	beq     write_false
	bne     write_true

write_false:
	cmp     r1, #0
	beq     write_false_no_newline
	bne     write_false_newline

write_false_no_newline:
	ldr     r12, =false_no_newline
	mov     r0, #5
	write_to_stdout r12, r0
	b       return_boolean

write_false_newline:
	ldr     r12, =false_newline
	mov     r0, #6
	write_to_stdout r12, r0
	b       return_boolean

write_true:
	cmp     r1, #0
	beq     write_true_no_newline
	bne     write_true_newline

write_true_no_newline:
	ldr     r12, =true_no_newline
	mov     r0, #4
	write_to_stdout r12, r0
	b       return_boolean

write_true_newline:
	ldr     r12, =true_newline
	mov     r0, #5
	write_to_stdout r12, r0
	b       return_boolean

return_boolean:
	mov     sp, r11
	pop     {r11, lr}
	bx      lr
