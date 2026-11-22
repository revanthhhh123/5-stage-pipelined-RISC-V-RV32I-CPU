# String processing: strlen, in-place upper-casing, in-place reverse,
# polynomial hash (h = h*31 + c), halfword memcpy. Exercises LB/LBU/SB/LHU/SH/LW.
# CHECK x11 30
# CHECK x10 0xf4c7e645
# CHECK x12 0x3703feef
        la   s0, str
        # --- strlen ---
        li   a1, 0
sl:     add  t0, s0, a1
        lbu  t1, 0(t0)
        beqz t1, sl_done
        addi a1, a1, 1
        j    sl
sl_done:
        # --- toupper in place ---
        li   t2, 0
up:     add  t0, s0, t2
        lbu  t1, 0(t0)
        beqz t1, up_done
        li   t3, 97
        blt  t1, t3, up_next
        li   t3, 122
        blt  t3, t1, up_next
        addi t1, t1, -32
        sb   t1, 0(t0)
up_next: addi t2, t2, 1
        j    up
up_done:
        # --- reverse in place (signed byte loads) ---
        li   t2, 0
        addi t3, a1, -1
rv:     bge  t2, t3, rv_done
        add  t0, s0, t2
        add  t4, s0, t3
        lb   t5, 0(t0)
        lb   t6, 0(t4)
        sb   t6, 0(t0)
        sb   t5, 0(t4)
        addi t2, t2, 1
        addi t3, t3, -1
        j    rv
rv_done:
        # --- hash: h = h*31 + c  (h<<5 - h + c) ---
        li   a0, 0
        li   t2, 0
hs:     add  t0, s0, t2
        lbu  t1, 0(t0)
        beqz t1, hs_done
        slli t3, a0, 5
        sub  t3, t3, a0
        add  a0, t3, t1
        addi t2, t2, 1
        j    hs
hs_done:
        # --- copy first 16 bytes with halfword ops, then sum the 4 words ---
        la   s1, dst
        li   t2, 0
cp:     add  t0, s0, t2
        add  t4, s1, t2
        lhu  t1, 0(t0)
        sh   t1, 0(t4)
        addi t2, t2, 2
        li   t3, 16
        blt  t2, t3, cp
        li   a2, 0
        lw   t0, 0(s1)
        add  a2, a2, t0
        lw   t0, 4(s1)
        add  a2, a2, t0
        lw   t0, 8(s1)
        add  a2, a2, t0
        lw   t0, 12(s1)
        add  a2, a2, t0
        ecall
.data
str: .asciz "Hello, Pipelined RISC-V World!"
.align 2
dst: .space 16
