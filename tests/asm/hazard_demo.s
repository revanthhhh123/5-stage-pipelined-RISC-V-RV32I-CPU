# Small program used to illustrate the pipeline (see docs/pipeline_trace.txt):
#   forwarding (EX/MEM and MEM/WB), a load-use stall, and loop-branch prediction.
# CHECK x7 12
# CHECK x29 24
        li   t0, 5
        li   t1, 7
        add  t2, t0, t1         # t2 = 12
        sub  t3, t2, t0         # needs t2 from EX/MEM  (forward)
        la   s0, buf
        sw   t2, 0(s0)
        lw   t4, 0(s0)
        add  t5, t4, t4         # load-use hazard -> 1 stall, then MEM/WB forward
        li   t6, 3
loop:   addi t6, t6, -1
        bnez t6, loop           # taken, taken, not-taken
        mv   t4, t5
        mv   t4, t5
        mv   t4, t5
        ecall
.data
buf: .word 0
