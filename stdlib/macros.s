.ifndef PLe0_MACROS
	.global PLe0_MACROS

@ pow
@
@ Calculate the the base elevated to the exponent
@   
@ Registers:
@  r0:     base 
@  r1:     exp 
@  r2:     total 
@
@ Labels:
@  1: main loop 
@  2: exit macro 
@ 
@ Returns:
@  r0: result 
.macro      pow     base, exp 
    mov     r0, \base   @ load base 
    mov     r1, \exp    @ load exp
    cmp     r1, #0      @ see if exp is zero 
    moveq   r2, #1      @ if yes, total will be 1 
    beq     2f
    mov     r2, r0      @ copy base to total
    sub     r1, #1      @ sub one off exp because we copied base 
1: 
    cmp     r1, #0      @ test if we need to multiply again 
    ble     2f          @ leave if eq or less than 0 
    mul     r2, r0 ,r2  @ multiply total by base and store in total 
    sub     r1, #1      @ decrement exp 
    b       1b 
2:
    mov     r0, r2      @ move result to r0
.endm 


@ write_to_stdout
@
@ Write the passed buffer to stdout for the given length
@
@ This macro saves and restores all the registers
@ 
@ Returns:
@  nothing
.macro      write_to_stdout     buffer, length
	push    {r0, r1, r2, r7}
	push    {\buffer}       @ put buffer in r1
	pop     {r1}
	push    {\length}       @ put length in r2
	pop     {r2}
    mov     r7, #4          @ 4 = write
    mov     r0, #1          @ 1 = stdout 
    svc     0 
	pop     {r0, r1, r2, r7}
.endm 


@ read_from stdin
@ 
@ Read from stdin to the passed buffer for the given length
@
@ This macro saves and restores all the registers except r0
@ 
@ Returns:
@  r0: how many bytes have been read
.macro      read_from_stdin     buffer, length
	push    {r1, r2, r7}
	push    {\buffer}       @ put buffer in r1
	pop     {r1}
	push    {\length}       @ put length in r2
	pop     {r2}
    mov     r7, #3          @ 3 = read
    mov     r0, #0          @ 0 = stdin
    svc     0 
	pop     {r1, r2, r7}
.endm 

.endif
