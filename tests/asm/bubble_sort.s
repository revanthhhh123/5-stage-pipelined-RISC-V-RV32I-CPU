# Bubble sort of 24 signed words, then verify order and checksum.
# CHECK x10 1
# CHECK x11 45140
        la   s0, arr
        li   s2, 24             # n (constant)
        mv   s1, s2             # current pass length
outer:  li   t0, 0              # swapped = 0
        li   t1, 1              # i = 1
inner:  bge  t1, s1, inner_done
        slli t2, t1, 2
        add  t2, t2, s0
        lw   t3, -4(t2)
        lw   t4, 0(t2)
        ble  t3, t4, noswap     # data-dependent, hard to predict
        sw   t4, -4(t2)
        sw   t3, 0(t2)
        li   t0, 1
noswap: addi t1, t1, 1
        j    inner
inner_done:
        addi s1, s1, -1
        bnez t0, outer
        # ---- verify sortedness + checksum ----
        li   a0, 1
        li   a1, 0
        li   t1, 0
chk:    slli t2, t1, 2
        add  t2, t2, s0
        lw   t3, 0(t2)
        add  a1, a1, t3
        beqz t1, nxt
        lw   t4, -4(t2)
        ble  t4, t3, nxt
        li   a0, 0              # out of order!
nxt:    addi t1, t1, 1
        blt  t1, s2, chk
        ecall
.data
arr: .word 2152, 735, 2734, 4832, -105, 93, 3889, 271, 2495, 4274, -25, 3656
     .word 1258, -193, 204, 3052, 2925, 72, 1471, 243, 4014, 2977, -16, 4132
