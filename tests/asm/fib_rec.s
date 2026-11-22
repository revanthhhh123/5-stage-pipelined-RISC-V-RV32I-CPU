# Recursive Fibonacci: fib(14) = 377.
# Stress test for JAL/JALR (call/return), stack traffic and load-use hazards.
# CHECK x10 377
        li   sp, 0x4000
        li   a0, 14
        jal  ra, fib
        ecall

fib:    li   t0, 2
        blt  a0, t0, fib_ret    # fib(0)=0, fib(1)=1
        addi sp, sp, -12
        sw   ra, 0(sp)
        sw   a0, 4(sp)
        addi a0, a0, -1
        jal  ra, fib            # fib(n-1)
        sw   a0, 8(sp)
        lw   a0, 4(sp)          # load-use: a0 consumed by next instruction
        addi a0, a0, -2
        jal  ra, fib            # fib(n-2)
        lw   t1, 8(sp)
        add  a0, a0, t1         # load-use again
        lw   ra, 0(sp)
        addi sp, sp, 12
fib_ret: ret                    # JALR: target depends on the call site
