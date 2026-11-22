# Bitwise CRC-32 (poly 0xEDB88320) over 64 bytes; compared against zlib.crc32.
# CHECK x10 0xffbae609
        la   s0, data
        li   s1, 64
        li   s2, 0xEDB88320
        li   a0, -1
        li   t0, 0
bloop:  add  t1, s0, t0
        lbu  t2, 0(t1)
        xor  a0, a0, t2
        li   t3, 8
bit:    andi t4, a0, 1
        srli a0, a0, 1
        beqz t4, noxor          # data-dependent: ~50% taken
        xor  a0, a0, s2
noxor:  addi t3, t3, -1
        bnez t3, bit
        addi t0, t0, 1
        blt  t0, s1, bloop
        not  a0, a0
        ecall
.data
data:
    .byte 11, 48, 85, 122, 159, 196, 233, 14, 51, 88, 125, 162, 199, 236, 17, 54
    .byte 91, 128, 165, 202, 239, 20, 57, 94, 131, 168, 205, 242, 23, 60, 97, 134
    .byte 171, 208, 245, 26, 63, 100, 137, 174, 211, 248, 29, 66, 103, 140, 177, 214
    .byte 251, 32, 69, 106, 143, 180, 217, 254, 35, 72, 109, 146, 183, 220, 1, 38
