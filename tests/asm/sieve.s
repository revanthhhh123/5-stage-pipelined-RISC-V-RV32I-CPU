# Sieve of Eratosthenes over [2,200): number of primes = 46. Uses byte loads/stores.
# CHECK x10 46
        la   s0, flags
        li   s1, 200
        li   t0, 0
        li   t2, 1
init:   add  t1, s0, t0
        sb   t2, 0(t1)
        addi t0, t0, 1
        blt  t0, s1, init
        li   t0, 2              # p
ploop:  add  t1, s0, t0
        lbu  t2, 0(t1)
        beqz t2, pnext          # load-use + data-dependent branch
        add  t3, t0, t0         # m = 2p
mloop:  bge  t3, s1, pnext
        add  t4, s0, t3
        sb   zero, 0(t4)
        add  t3, t3, t0
        j    mloop
pnext:  addi t0, t0, 1
        li   t5, 15             # p*p < 200  <=>  p <= 14
        blt  t0, t5, ploop
        li   a0, 0
        li   t0, 2
cnt:    add  t1, s0, t0
        lbu  t2, 0(t1)
        add  a0, a0, t2
        addi t0, t0, 1
        blt  t0, s1, cnt
        ecall
.data
flags: .space 200
