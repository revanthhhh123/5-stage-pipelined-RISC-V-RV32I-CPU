# Iterative Fibonacci: fib(20) = 6765, also stores the sequence to memory.
# CHECK x10 0x1a6d
        li   t0, 0              # F(n)
        li   t1, 1              # F(n+1)
        li   t2, 20             # iterations
        la   s0, results
loop:   sw   t0, 0(s0)
        add  t3, t0, t1         # back-to-back RAW dependencies -> forwarding
        mv   t0, t1
        mv   t1, t3
        addi s0, s0, 4
        addi t2, t2, -1
        bnez t2, loop           # well-predicted backward branch
        mv   a0, t0
        ecall
.data
results: .space 80
