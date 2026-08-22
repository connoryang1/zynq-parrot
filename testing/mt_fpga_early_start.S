#include "asm.h"

    .section .text.init
    .global _start
    .type _start, @function
_start:
    /* Host character register. This works before gp, sp, TLS, or libc exist. */
    li t0, 0x00101000
    li t1, 'A'
    sb t1, 0(t0)

    la t1, early_trap_entry
    csrw mtvec, t1

    li t1, 'B'
    sb t1, 0(t0)
    tail dramfs_start

    .align 2
early_trap_entry:
    li t0, 0x00101000
    li t1, '!'
    sb t1, 0(t0)
    csrr t1, mcause
    j raw_hex_loop

raw_hex_loop:
    li t2, 16
1:
    srli t3, t1, 60
    li t4, 10
    bltu t3, t4, 2f
    addi t3, t3, ('a' - 10)
    j 3f
2:
    addi t3, t3, '0'
3:
    sb t3, 0(t0)
    slli t1, t1, 4
    addi t2, t2, -1
    bnez t2, 1b
    li t1, '\n'
    sb t1, 0(t0)
4:
    wfi
    j 4b

