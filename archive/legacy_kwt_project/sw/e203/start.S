#include "kwt_e203_layout.h"
    .section .text.start,"ax",@progbits
    .globl _start
    .option norvc
    .option norelax
_start:
    la sp, __stack_top
    csrw mie, zero
    la t0, trap_handler
    csrw mtvec, t0
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sw zero, 0(t0)
    addi t0, t0, 4
    j 1b
2:  call main
3:  j 3b
    .balign 4
trap_handler:
    li t0, KWT_MAILBOX
    csrr t1, mcause
    sw t1, 28(t0)
    csrr t1, mepc
    sw t1, 32(t0)
    csrr t1, mtval
    sw t1, 36(t0)
    fence iorw, iorw
    li t1, 0x4b575454
    sw t1, 0(t0)
    fence iorw, iorw
4:  j 4b
