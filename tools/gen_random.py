#!/usr/bin/env python3
"""
gen_random.py - constrained-random RV32I program generator

Generates always-terminating programs that deliberately stress the pipeline:
  * long RAW dependency chains (sources biased to recently written registers)
  * load -> use sequences (load-use stalls), store -> load round trips
  * byte / half / word accesses to a 256-byte scratch buffer
  * forward branches of every type, counted loops (nested), JAL / JALR,
    leaf subroutine calls and returns
  * writes to x0, back-to-back branches, AUIPC / LUI, etc.

Reserved registers:  x1 ra | x28 buffer base | x29 scratch | x30,x31 loop counters
"""
import random
import sys

POOL = list(range(5, 28))                # general purpose registers used as dest/src
R_OPS = ['add', 'sub', 'sll', 'slt', 'sltu', 'xor', 'srl', 'sra', 'or', 'and']
I_OPS = ['addi', 'slti', 'sltiu', 'xori', 'ori', 'andi']
SH_OPS = ['slli', 'srli', 'srai']
BR_OPS = ['beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu']
SPECIAL = [0, 1, -1, 0x7FFFFFFF, -0x80000000, 0x80000000, 0xFF, 0xFFFF, 0x55555555, -2]


class Gen:
    def __init__(self, seed):
        self.r = random.Random(seed)
        self.lines = []
        self.lab = 0
        self.recent = [5, 6, 7]
        self.subs = []
        self.depth = 0

    def emit(self, s): self.lines.append('        ' + s)
    def label(self, l): self.lines.append(l + ':')
    def newlab(self, p='L'):
        self.lab += 1
        return '%s%d' % (p, self.lab)

    def dst(self):
        if self.r.random() < 0.04:
            return 0
        d = self.r.choice(POOL)
        self.recent = (self.recent + [d])[-4:]
        return d

    def src(self):
        c = self.r.random()
        if c < 0.55: return self.r.choice(self.recent)
        if c < 0.62: return 0
        return self.r.choice(POOL)

    def imm12(self):
        c = self.r.random()
        if c < 0.2: return self.r.choice([-2048, -1, 0, 1, 2047])
        return self.r.randint(-2048, 2047)

    # ------------------------------ instruction kinds ------------------------
    def alu_r(self):
        self.emit('%s x%d, x%d, x%d' % (self.r.choice(R_OPS), self.dst(), self.src(), self.src()))

    def alu_i(self):
        if self.r.random() < 0.3:
            self.emit('%s x%d, x%d, %d' % (self.r.choice(SH_OPS), self.dst(), self.src(), self.r.randint(0, 31)))
        else:
            self.emit('%s x%d, x%d, %d' % (self.r.choice(I_OPS), self.dst(), self.src(), self.imm12()))

    def upper(self):
        self.emit('%s x%d, %d' % (self.r.choice(['lui', 'auipc']), self.dst(), self.r.randint(0, 0xFFFFF)))

    def mem_op(self):
        kind = self.r.choice(['lw', 'lh', 'lhu', 'lb', 'lbu', 'sw', 'sh', 'sb'])
        size = {'w': 4, 'h': 2, 'b': 1}[kind[1]]
        off = self.r.randrange(0, 256 // size) * size
        if kind[0] == 'l':
            d = self.dst()
            self.emit('%s x%d, %d(x28)' % (kind, d, off))
            if self.r.random() < 0.6:                       # immediate consumer -> load-use
                self.emit('%s x%d, x%d, x%d' % (self.r.choice(R_OPS), self.dst(), d, self.src()))
        else:
            self.emit('%s x%d, %d(x28)' % (kind, self.src(), off))
            if self.r.random() < 0.4:                       # store -> load same address
                self.emit('lw x%d, %d(x28)' % (self.dst(), off & ~3))

    def simple(self):
        c = self.r.random()
        if c < 0.40: self.alu_r()
        elif c < 0.70: self.alu_i()
        elif c < 0.78: self.upper()
        else: self.mem_op()

    def fwd_branch(self):
        l = self.newlab()
        self.emit('%s x%d, x%d, %s' % (self.r.choice(BR_OPS), self.src(),
                                       self.src() if self.r.random() < 0.8 else 0, l))
        for _ in range(self.r.randint(0, 3)): self.simple()
        self.label(l)

    def fwd_jal(self):
        l = self.newlab()
        d = self.r.choice([0, 0, self.r.choice(POOL)])
        if d: self.recent = (self.recent + [d])[-4:]
        self.emit('jal x%d, %s' % (d, l))
        for _ in range(self.r.randint(1, 2)): self.simple()          # skipped
        self.label(l)

    def fwd_jalr(self):
        l = self.newlab()
        d = self.r.choice([0, self.r.choice(POOL)])
        if d: self.recent = (self.recent + [d])[-4:]
        self.emit('la x29, %s' % l)
        self.emit('jalr x%d, %d(x29)' % (d, self.r.choice([0, 0, 1])))   # bit0 must be cleared by HW
        for _ in range(self.r.randint(1, 2)): self.simple()
        self.label(l)

    def call(self):
        if not self.subs:
            return
        s = self.r.choice(self.subs)
        if self.r.random() < 0.5:
            self.emit('jal ra, %s' % s)
        else:
            self.emit('la x29, %s' % s)
            self.emit('jalr ra, 0(x29)')

    def loop(self):
        reg = 30 if self.depth == 0 else 31
        l = self.newlab('LOOP')
        self.emit('li x%d, %d' % (reg, self.r.randint(2, 9 if self.depth == 0 else 4)))
        self.label(l)
        self.depth += 1
        for _ in range(self.r.randint(2, 7)):
            self.block(allow_loop=(self.depth < 2))
        self.depth -= 1
        self.emit('addi x%d, x%d, -1' % (reg, reg))
        self.emit('bnez x%d, %s' % (reg, l))

    def block(self, allow_loop=True):
        c = self.r.random()
        if c < 0.55: self.simple()
        elif c < 0.70: self.fwd_branch()
        elif c < 0.76: self.fwd_jal()
        elif c < 0.80: self.fwd_jalr()
        elif c < 0.88: self.call()
        elif allow_loop and c < 0.95: self.loop()
        else: self.simple()

    # -------------------------------- program --------------------------------
    def build(self):
        r = self.r
        nsub = r.randint(1, 3)
        self.subs = ['sub%d' % i for i in range(nsub)]
        self.lines.append('# random program, auto-generated by tools/gen_random.py')
        self.emit('la x28, buf')
        for reg in POOL:
            v = r.choice(SPECIAL) if r.random() < 0.3 else r.randint(-(1 << 31), (1 << 31) - 1)
            self.emit('li x%d, %d' % (reg, v))
        for _ in range(r.randint(40, 110)):
            self.block()
        self.emit('ecall')
        for s in self.subs:                                  # leaf subroutines (no loops)
            self.label(s)
            for _ in range(r.randint(2, 6)): self.simple()
            if r.random() < 0.5: self.fwd_branch()
            self.emit('ret')
        self.lines.append('.data')
        self.lines.append('buf:')
        for i in range(0, 64, 8):
            self.lines.append('    .word ' + ', '.join(str(r.randint(0, 0xFFFFFFFF)) for _ in range(8)))
        return '\n'.join(self.lines) + '\n'


def generate(seed, path):
    open(path, 'w').write(Gen(seed).build())


if __name__ == '__main__':
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    sys.stdout.write(Gen(seed).build())
