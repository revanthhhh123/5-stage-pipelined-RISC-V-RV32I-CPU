#!/usr/bin/env python3
"""
rviss.py - RV32I instruction-set simulator (golden reference model).

Written independently from the RTL (different structure, decodes from the
architectural spec) and used by the regression to compare the final
architectural state (registers + data memory + retired-instruction count)
against the pipelined Verilog core.

Memory model matches the RTL: 16 KiB, addresses wrap, separate instruction
and data copies of the loaded image, no misaligned access support.
"""
import sys
import argparse

MASK = 0xFFFFFFFF
MEM_WORDS = 4096


class SimError(Exception):
    pass


def s32(v):
    v &= MASK
    return v - (1 << 32) if v & 0x80000000 else v


def sext(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


class ISS:
    def __init__(self, words):
        self.imem = [0x13] * MEM_WORDS
        self.dmem = bytearray(MEM_WORDS * 4)
        for i, w in enumerate(words[:MEM_WORDS]):
            self.imem[i] = w & MASK
            self.dmem[4 * i:4 * i + 4] = (w & MASK).to_bytes(4, 'little')
        self.x = [0] * 32
        self.pc = 0
        self.instret = 0
        self.halted = False
        self.branches = 0
        self.taken = 0
        self.loads = 0
        self.stores = 0

    # ---- memory ----
    def _addr(self, a, size):
        if a & (size - 1):
            raise SimError('misaligned access %#x (size %d) at pc=%#x' % (a, size, self.pc))
        return a & (MEM_WORDS * 4 - 1)

    def load(self, a, size, signed):
        a = self._addr(a, size)
        v = int.from_bytes(self.dmem[a:a + size], 'little')
        return sext(v, 8 * size) & MASK if signed else v

    def store(self, a, size, v):
        a = self._addr(a, size)
        self.dmem[a:a + size] = (v & ((1 << (8 * size)) - 1)).to_bytes(size, 'little')

    # ---- execution ----
    def wr(self, rd, v):
        if rd:
            self.x[rd] = v & MASK

    def step(self):
        pc = self.pc
        ins = self.imem[(pc >> 2) & (MEM_WORDS - 1)]
        op = ins & 0x7F
        rd = (ins >> 7) & 31
        f3 = (ins >> 12) & 7
        rs1 = (ins >> 15) & 31
        rs2 = (ins >> 20) & 31
        f7 = ins >> 25
        a, b = self.x[rs1], self.x[rs2]
        npc = (pc + 4) & MASK
        imm_i = sext(ins >> 20, 12)
        self.instret += 1

        if op == 0x37:   self.wr(rd, ins & 0xFFFFF000)
        elif op == 0x17: self.wr(rd, pc + (ins & 0xFFFFF000))
        elif op == 0x6F:
            imm = sext(((ins >> 31) << 20) | (((ins >> 12) & 0xFF) << 12) |
                       (((ins >> 20) & 1) << 11) | (((ins >> 21) & 0x3FF) << 1), 21)
            self.wr(rd, pc + 4); npc = (pc + imm) & MASK
        elif op == 0x67:
            t = ((a + imm_i) & MASK) & ~1
            self.wr(rd, pc + 4); npc = t
        elif op == 0x63:
            imm = sext(((ins >> 31) << 12) | (((ins >> 7) & 1) << 11) |
                       (((ins >> 25) & 0x3F) << 5) | (((ins >> 8) & 0xF) << 1), 13)
            c = {0: a == b, 1: a != b, 4: s32(a) < s32(b), 5: s32(a) >= s32(b),
                 6: a < b, 7: a >= b}.get(f3)
            if c is None: raise SimError('illegal branch funct3 at pc=%#x' % pc)
            self.branches += 1
            if c:
                self.taken += 1
                npc = (pc + imm) & MASK
        elif op == 0x03:
            addr = (a + imm_i) & MASK
            m = {0: (1, True), 1: (2, True), 2: (4, False), 4: (1, False), 5: (2, False)}.get(f3)
            if m is None: raise SimError('illegal load at pc=%#x' % pc)
            self.loads += 1
            self.wr(rd, self.load(addr, m[0], m[1]))
        elif op == 0x23:
            imm = sext(((ins >> 25) << 5) | ((ins >> 7) & 31), 12)
            size = {0: 1, 1: 2, 2: 4}.get(f3)
            if size is None: raise SimError('illegal store at pc=%#x' % pc)
            self.stores += 1
            self.store((a + imm) & MASK, size, b)
        elif op in (0x13, 0x33):
            y = imm_i if op == 0x13 else s32(b)
            ub = y & MASK
            sh = ub & 31
            sub = (op == 0x33) and (f7 == 0x20)
            if f3 == 0:   r = a - ub if sub else a + ub
            elif f3 == 1: r = a << sh
            elif f3 == 2: r = int(s32(a) < s32(ub))
            elif f3 == 3: r = int(a < ub)
            elif f3 == 4: r = a ^ ub
            elif f3 == 5: r = (s32(a) >> sh) if (ins >> 30) & 1 else (a >> sh)
            elif f3 == 6: r = a | ub
            else:         r = a & ub
            self.wr(rd, r)
        elif op == 0x0F:
            pass
        elif op == 0x73:
            self.halted = True
        else:
            raise SimError('illegal instruction %#010x at pc=%#x' % (ins, pc))
        self.pc = npc

    def run(self, max_steps=5_000_000):
        while not self.halted:
            if self.instret >= max_steps:
                raise SimError('step limit reached')
            self.step()
        return self.instret

    # ---- dumps (same format as the RTL testbench) ----
    def regs_text(self):
        return ''.join('%08x\n' % v for v in self.x)

    def mem_text(self):
        return ''.join('%08x\n' % int.from_bytes(self.dmem[i:i + 4], 'little')
                       for i in range(0, MEM_WORDS * 4, 4))


def read_hex(path):
    with open(path) as f:
        return [int(l.strip(), 16) for l in f if l.strip()]


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='RV32I golden-model simulator')
    ap.add_argument('hexfile')
    ap.add_argument('--out', help='write <out>.regs and <out>.mem')
    args = ap.parse_args()
    s = ISS(read_hex(args.hexfile))
    try:
        n = s.run()
    except SimError as e:
        sys.exit('ISS error: %s' % e)
    print('retired %d instructions' % n)
    for i in range(0, 32, 4):
        print('  '.join('x%-2d=%08x' % (j, s.x[j]) for j in range(i, i + 4)))
    if args.out:
        open(args.out + '.regs', 'w').write(s.regs_text())
        open(args.out + '.mem', 'w').write(s.mem_text())
