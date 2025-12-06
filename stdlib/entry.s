.text
.arch armv6
.syntax unified

.global _start

@ Entry point as wanted by ld
@   * reset fp and lr, to define "the outermost frame" (glibc)
@   * call main
@   * call the exit syscall with the exit value returned from main
_start:
	mov     fp, #0
	mov     lr, #0

	bl      main

	@ the exit value will be the one returned from main
    mov     r7, #1          @ 1 = exit
	svc     0
