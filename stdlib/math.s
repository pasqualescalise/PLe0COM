.text
.arch armv6
.syntax unified

.include "stdlib/macros.s"


.global __modsi3

@ Calculate r0 mod r1
@
@ TODO: needs a way to check for numbers <= 0, or maybe we can do it in the compiler
@
@ Parameters:
@  r0: number to proces
@  r1: modulus
@ 
@ Returns:
@  r0 % r1
__modsi3:
	push    {r11, lr}
	mov r11, sp

modsi3_loop_start:
	cmp     r0, r1
	blt     modsi3_end

	sub     r0, r1              @ modulus as a loop of subtractions
	b       modsi3_loop_start

modsi3_end:
	mov     sp, r11
	pop     {r11, lr}
	bx      lr
