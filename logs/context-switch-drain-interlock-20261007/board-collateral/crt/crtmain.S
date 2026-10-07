#include "asm.h"

    .section .text.init

    .macro ENTER func
    /* Default to empty argument vector */
    LREG a0, __argc     /* argc = 1 */
    la a1, __argv       /* argv = { name, NULL } */
    call \func
    tail exit
    .endm

    .global _start_main
    .type _start_main, @function
_start_main:
    BARRIER_PASS __boot_sync
    ENTER main

    .global _start_secondary
    .type _start_secondary, @function
_start_secondary:
    /* Synchronize secondary harts */
    BARRIER_WAIT __boot_sync
    ENTER __main

.section .bss
__boot_sync:
    .word 0

.section .rodata
.align 3
.weak __argc
.weak __argv
.weak environ
__argc:
    .dword 1
__argv:
    .dc.a name
    .dc.a 0
name:
    .asciz "panicroom"

