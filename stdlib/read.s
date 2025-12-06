.text
.arch armv6
.syntax unified

.include "stdlib/macros.s"


.global __pl0_read

@ TODO: not in use at the moment
@
@ Read a number string from stdin, convert it to an integer,
@ then return it
@
@ Registers:     
@  r4:  address of the next place to read from
@  r5:  accumulator for the final number
@  r6:  set to 1 if the number passed starts with a '-'
@  r8:  keeps track of how many bytes we have read
@
@ Returns:
@  r0: read number
__pl0_read: 
	push    {r4, r5, r6, r8, r11, lr}
	mov     r11, sp

	mov     r5, #0
	mov     r8, #0

	sub     sp, sp, #4          @ the read string is kept on the stack
	mov     r4, sp

read_loop:
	mov     r12, #4             @ read 4 bytes from stdin
	read_from_stdin r4, r12

	cmp     r0, #1              @ if we have read more than 1 byte, keep going
	bne     continue

	cmp     r8, #0              @ if we have read 1 byte, but we are not at the
	bne     continue            @ start, keep going

	mov     r5, #0              @ error: we have read a single \n, return a 0
	b       return_read

continue:
	add r8, r8, r0              @ increment counter

	pop {r12}                   @ reverse the order of the read bytes
	rev r12, r12
	push {r12}

	cmp r0, #4                  @ if we have read less than 4 bytes, stop reading
	blt end_read

	ldrb r12, [sp]              @ if we have read 4 bytes and the last one is
	cmp r12, #'\n'              @ a '\n', stop reading
	beq end_read

	sub sp, sp, #4              @ if we have read 4 bytes but no '\n', keep going
	mov r4, sp                  @ by allocating 4 new bytes on the stack
	b read_loop

end_read:
	sub r8, r8, #2              @ remove the newline and the last char
	sub r4, r11, #1             @ reposition r4 at the first char

	mov r6, #0                  @ if the first char is not a '-', we can start converting
	ldrb r12, [r4]
	cmp r12, #'-'
	bne convert_digit

	sub r4, r4, #1              @ if the first char is a '-', set r6 to 1 and update counters
	sub r8, r8, #1
	mov r6, #1
	
convert_digit:
	cmp r8, #0
	beq add_last_number

	ldrb r12, [r4], #-1         @ get the next number into r12
	sub r12, r12, #'0'          @ convert it to ASCII

	pow #10, r8                 @ get 10^r8, where r8 is the position of the current digit in our final number
	mul r12, r12, r0            @ multiply the power to the number to get its positional value
	add r5, r5, r12             @ update the accumulator

	sub r8, r8, #1
	b convert_digit

add_last_number:
	ldrb r12, [r4], #-1
	sub r12, r12, #'0'
	add r5, r5, r12

	cmp r6, #0
	beq return_read

	sub r5, r5, #1              @ turn the number negative
	mvn r5, r5

return_read:
	mov r0, r5                  @ put the number in r0

	mov sp, r11
	pop {r4, r5, r6, r8, r11, lr}
	bx lr
