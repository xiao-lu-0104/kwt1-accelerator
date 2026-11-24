#include "SharedLayout.h"
    .section .text.start,"ax",@progbits
    .globl _start
_start:
    // The E203 register file has no reset. Define the initial architectural
    // state before C function prologues save callee-saved registers to TCM.
    .option push
    .option norvc
    .irp reg,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31
    addi x\reg, x0, 0
    .endr
    .option pop
    .option push
    .option norelax
    la sp, StackTop
    la t0, Trap
    csrw mtvec, t0
    la t0, DataLoad
    la t1, DataStart
    la t2, DataEnd
1:
    bgeu t1, t2, 2f
    lw t3, 0(t0)
    sw t3, 0(t1)
    addi t0, t0, 4
    addi t1, t1, 4
    j 1b
2:
    la t0, BssStart
    la t1, BssEnd
3:
    bgeu t0, t1, 4f
    sw zero, 0(t0)
    addi t0, t0, 4
    j 3b
4:
    .option pop
    call Main
5:
    wfi
    j 5b

    .section .text.trap,"ax",@progbits
    .balign 64
Trap:
    li t0, TPU_MAILBOX
    csrr t1, mcause
    sw t1, 32(t0)
    csrr t1, mepc
    sw t1, 36(t0)
    li t1, 3
    sw t1, 8(t0)
    j 5b
