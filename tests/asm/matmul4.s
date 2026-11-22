# 4x4 integer matrix multiply C = A*B using a software shift-add multiplier
# (RV32I has no MUL). Result checksum = sum of all C elements = 1215.
# CHECK x10 1215
        li   sp, 0x4000
        la   s0, A
        la   s1, B
        la   s2, C
        li   s3, 0              # i
iloop:  li   s4, 0              # j
jloop:  li   s5, 0              # k
        li   s6, 0              # acc
kloop:  slli t2, s3, 2
        add  t2, t2, s5
        slli t2, t2, 2
        add  t2, t2, s0
        lw   a0, 0(t2)          # A[i][k]
        slli t3, s5, 2
        add  t3, t3, s4
        slli t3, t3, 2
        add  t3, t3, s1
        lw   a1, 0(t3)          # B[k][j]
        jal  ra, mul
        add  s6, s6, a0
        addi s5, s5, 1
        li   t4, 4
        blt  s5, t4, kloop
        slli t2, s3, 2
        add  t2, t2, s4
        slli t2, t2, 2
        add  t2, t2, s2
        sw   s6, 0(t2)          # C[i][j]
        addi s4, s4, 1
        li   t4, 4
        blt  s4, t4, jloop
        addi s3, s3, 1
        li   t4, 4
        blt  s3, t4, iloop
        # checksum of C
        li   a0, 0
        li   t0, 0
sum:    slli t1, t0, 2
        add  t1, t1, s2
        lw   t2, 0(t1)
        add  a0, a0, t2
        addi t0, t0, 1
        li   t3, 16
        blt  t0, t3, sum
        ecall

mul:    li   t0, 0              # a0 = a0 * a1 (unsigned shift-add)
mloop:  beqz a1, mdone
        andi t1, a1, 1
        beqz t1, mskip
        add  t0, t0, a0
mskip:  slli a0, a0, 1
        srli a1, a1, 1
        j    mloop
mdone:  mv   a0, t0
        ret
.data
A: .word 2,3,4,5, 6,7,1,2, 3,4,5,6, 7,1,2,3
B: .word 6,8,1,3, 9,2,4,6, 3,5,7,9, 6,8,1,3
C: .space 64
