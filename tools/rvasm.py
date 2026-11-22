#!/usr/bin/env python3
"""
rvasm.py - small two-pass RV32I assembler (no external toolchain needed).

Features
  * all RV32I base instructions (except FENCE.I / CSR)
  * common pseudo-instructions: nop li la mv not neg seqz snez j jr ret jal jalr
    beqz bnez blez bgez bltz bgtz bgt ble bgtu bleu ecall ebreak
  * directives: .text .data .word .half .byte .space .asciz .string .align .equ
  * labels, character/hex/decimal immediates, simple expressions (label+4, 1<<5)
Outputs
  <out>.hex  one 32-bit word per line ($readmemh compatible, word 0 = address 0)
  <out>.lst  address / machine word / source listing (used by pipeview.py)
"""
import re
import sys
import argparse

ABI = {'zero': 0, 'ra': 1, 'sp': 2, 'gp': 3, 'tp': 4, 'fp': 8}
for i in range(3):  ABI['t%d' % i] = 5 + i
for i in range(2):  ABI['s%d' % i] = 8 + i
for i in range(8):  ABI['a%d' % i] = 10 + i
for i in range(2, 12): ABI['s%d' % i] = 16 + i
for i in range(3, 7):  ABI['t%d' % i] = 25 + i
for i in range(32):    ABI['x%d' % i] = i

R_OPS  = {'add': (0, 0), 'sub': (0x20, 0), 'sll': (0, 1), 'slt': (0, 2), 'sltu': (0, 3),
          'xor': (0, 4), 'srl': (0, 5), 'sra': (0x20, 5), 'or': (0, 6), 'and': (0, 7)}
I_OPS  = {'addi': 0, 'slti': 2, 'sltiu': 3, 'xori': 4, 'ori': 6, 'andi': 7}
SH_OPS = {'slli': (0, 1), 'srli': (0, 5), 'srai': (0x20, 5)}
LOADS  = {'lb': 0, 'lh': 1, 'lw': 2, 'lbu': 4, 'lhu': 5}
STORES = {'sb': 0, 'sh': 1, 'sw': 2}
BRANCH = {'beq': 0, 'bne': 1, 'blt': 4, 'bge': 5, 'bltu': 6, 'bgeu': 7}


class AsmError(Exception):
    pass


def reg(tok, ln):
    t = tok.strip().lower()
    if t not in ABI:
        raise AsmError("line %d: bad register '%s'" % (ln, tok))
    return ABI[t]


def split_ops(s):
    out, cur, depth, inq = [], '', 0, False
    for ch in s:
        if ch == '"':
            inq = not inq
        if ch == '(' and not inq: depth += 1
        if ch == ')' and not inq: depth -= 1
        if ch == ',' and depth == 0 and not inq:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def strip_comment(line):
    out, inq = '', False
    for i, ch in enumerate(line):
        if ch == '"':
            inq = not inq
        if not inq and (ch == '#' or line[i:i + 2] == '//'):
            break
        out += ch
    return out


def sx(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def hi_lo(v):
    v &= 0xFFFFFFFF
    lo = sx(v, 12)
    hi = ((v - lo) >> 12) & 0xFFFFF
    return hi, lo


# ------------------------------- encoders ------------------------------------
def e_r(f7, rs2, rs1, f3, rd, op): return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op
def e_i(imm, rs1, f3, rd, op):     return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op
def e_s(imm, rs2, rs1, f3, op):
    return (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op
def e_b(imm, rs2, rs1, f3, op):
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | \
           (f3 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | op
def e_u(imm20, rd, op):            return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | op
def e_j(imm, rd, op):
    return (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3FF) << 21) | (((imm >> 11) & 1) << 20) | \
           (((imm >> 12) & 0xFF) << 12) | (rd << 7) | op


class Assembler:
    def __init__(self):
        self.consts = {}
        self.labels = {}      # name -> (section, offset)
        self.items = {'text': [], 'data': []}
        self.size = {'text': 0, 'data': 0}
        self.syms = {}

    # ---------------------------- expression eval ----------------------------
    def ev(self, expr, ln, final=True):
        e = expr.strip()
        if re.fullmatch(r"'.'", e):
            return ord(e[1])
        env = dict(self.consts)
        if final:
            env.update(self.syms)
        try:
            return int(eval(e, {"__builtins__": {}}, env))
        except Exception:
            raise AsmError("line %d: cannot evaluate '%s'" % (ln, expr))

    # --------------------------- pseudo expansion ----------------------------
    def li_len(self, ops, ln):
        v = self.ev(ops[1], ln, final=False)
        v = sx(v, 32)
        if -2048 <= v < 2048:
            return 1
        _, lo = hi_lo(v)
        return 1 if lo == 0 else 2

    def length(self, mn, ops, ln):
        if mn == 'li': return self.li_len(ops, ln)
        if mn == 'la': return 2
        return 1

    def expand(self, mn, ops, ln):
        """pseudo -> list of (mnemonic, operands) real instructions"""
        n = len(ops)
        if mn == 'nop':   return [('addi', ['x0', 'x0', '0'])]
        if mn == 'mv':    return [('addi', [ops[0], ops[1], '0'])]
        if mn == 'not':   return [('xori', [ops[0], ops[1], '-1'])]
        if mn == 'neg':   return [('sub', [ops[0], 'x0', ops[1]])]
        if mn == 'seqz':  return [('sltiu', [ops[0], ops[1], '1'])]
        if mn == 'snez':  return [('sltu', [ops[0], 'x0', ops[1]])]
        if mn == 'j':     return [('jal', ['x0', ops[0]])]
        if mn == 'jal' and n == 1: return [('jal', ['ra', ops[0]])]
        if mn == 'jr':    return [('jalr', ['x0', '0(%s)' % ops[0]])]
        if mn == 'jalr' and n == 1: return [('jalr', ['ra', '0(%s)' % ops[0]])]
        if mn == 'ret':   return [('jalr', ['x0', '0(ra)'])]
        if mn == 'beqz':  return [('beq', [ops[0], 'x0', ops[1]])]
        if mn == 'bnez':  return [('bne', [ops[0], 'x0', ops[1]])]
        if mn == 'blez':  return [('bge', ['x0', ops[0], ops[1]])]
        if mn == 'bgez':  return [('bge', [ops[0], 'x0', ops[1]])]
        if mn == 'bltz':  return [('blt', [ops[0], 'x0', ops[1]])]
        if mn == 'bgtz':  return [('blt', ['x0', ops[0], ops[1]])]
        if mn == 'bgt':   return [('blt', [ops[1], ops[0], ops[2]])]
        if mn == 'ble':   return [('bge', [ops[1], ops[0], ops[2]])]
        if mn == 'bgtu':  return [('bltu', [ops[1], ops[0], ops[2]])]
        if mn == 'bleu':  return [('bgeu', [ops[1], ops[0], ops[2]])]
        if mn == 'li':
            v = sx(self.ev(ops[1], ln), 32)
            if -2048 <= v < 2048:
                return [('addi', [ops[0], 'x0', str(v)])]
            hi, lo = hi_lo(v)
            if lo == 0:
                return [('lui', [ops[0], str(hi)])]
            return [('lui', [ops[0], str(hi)]), ('addi', [ops[0], ops[0], str(lo)])]
        if mn == 'la':
            hi, lo = hi_lo(self.ev(ops[1], ln))
            return [('lui', [ops[0], str(hi)]), ('addi', [ops[0], ops[0], str(lo)])]
        return [(mn, ops)]

    # ------------------------------ encoding ---------------------------------
    def mem_operand(self, s, ln):
        m = re.fullmatch(r"(.*)\(\s*(\w+)\s*\)", s.strip())
        if not m:
            raise AsmError("line %d: bad memory operand '%s'" % (ln, s))
        off = m.group(1).strip()
        return (self.ev(off, ln) if off else 0), reg(m.group(2), ln)

    def encode(self, mn, ops, pc, ln):
        def chk(v, bits, what):
            if not (-(1 << (bits - 1)) <= v < (1 << (bits - 1))):
                raise AsmError("line %d: %s %d out of range" % (ln, what, v))
            return v
        try:
            if mn in R_OPS:
                f7, f3 = R_OPS[mn]
                return e_r(f7, reg(ops[2], ln), reg(ops[1], ln), f3, reg(ops[0], ln), 0x33)
            if mn in I_OPS:
                return e_i(chk(self.ev(ops[2], ln), 12, 'imm'), reg(ops[1], ln), I_OPS[mn], reg(ops[0], ln), 0x13)
            if mn in SH_OPS:
                f7, f3 = SH_OPS[mn]
                sh = self.ev(ops[2], ln)
                if not 0 <= sh < 32: raise AsmError("line %d: bad shift amount" % ln)
                return e_i((f7 << 5) | sh, reg(ops[1], ln), f3, reg(ops[0], ln), 0x13)
            if mn in LOADS:
                off, rs1 = self.mem_operand(ops[1], ln)
                return e_i(chk(off, 12, 'offset'), rs1, LOADS[mn], reg(ops[0], ln), 0x03)
            if mn in STORES:
                off, rs1 = self.mem_operand(ops[1], ln)
                return e_s(chk(off, 12, 'offset'), reg(ops[0], ln), rs1, STORES[mn], 0x23)
            if mn in BRANCH:
                off = self.ev(ops[2], ln) - pc
                chk(off, 13, 'branch offset')
                if off & 1: raise AsmError("line %d: misaligned branch target" % ln)
                return e_b(off, reg(ops[1], ln), reg(ops[0], ln), BRANCH[mn], 0x63)
            if mn == 'lui':   return e_u(self.ev(ops[1], ln), reg(ops[0], ln), 0x37)
            if mn == 'auipc': return e_u(self.ev(ops[1], ln), reg(ops[0], ln), 0x17)
            if mn == 'jal':
                off = self.ev(ops[1], ln) - pc
                chk(off, 21, 'jump offset')
                return e_j(off, reg(ops[0], ln), 0x6F)
            if mn == 'jalr':
                if len(ops) == 2:
                    off, rs1 = self.mem_operand(ops[1], ln)
                else:
                    rs1, off = reg(ops[1], ln), self.ev(ops[2], ln)
                return e_i(chk(off, 12, 'offset'), rs1, 0, reg(ops[0], ln), 0x67)
            if mn == 'ecall':  return 0x00000073
            if mn == 'ebreak': return 0x00100073
            if mn == 'fence':  return 0x0000000F
        except IndexError:
            raise AsmError("line %d: wrong operand count for '%s'" % (ln, mn))
        raise AsmError("line %d: unknown instruction '%s'" % (ln, mn))

    # ------------------------------- passes ----------------------------------
    def pass1(self, text):
        sec = 'text'
        for ln, raw in enumerate(text.splitlines(), 1):
            line = strip_comment(raw).strip()
            while True:
                m = re.match(r"^([A-Za-z_.$][\w.$]*)\s*:\s*(.*)$", line)
                if not m: break
                self.labels[m.group(1)] = (sec, self.size[sec])
                line = m.group(2).strip()
            if not line:
                continue
            parts = line.split(None, 1)
            mn = parts[0].lower()
            ops = split_ops(parts[1]) if len(parts) > 1 else []
            if mn == '.text': sec = 'text'; continue
            if mn == '.data': sec = 'data'; continue
            if mn == '.equ':
                self.consts[ops[0]] = self.ev(ops[1], ln, final=False); continue
            if mn == '.align':
                a = 1 << self.ev(ops[0], ln, final=False)
                pad = (-self.size[sec]) % a
                self.items[sec].append((self.size[sec], '.space', [str(pad)], ln, raw))
                self.size[sec] += pad; continue
            if mn.startswith('.'):
                n = self.directive_size(mn, ops, ln)
                self.items[sec].append((self.size[sec], mn, ops, ln, raw))
                self.size[sec] += n; continue
            if sec != 'text':
                raise AsmError("line %d: instruction in .data section" % ln)
            n = 4 * self.length(mn, ops, ln)
            self.items[sec].append((self.size[sec], mn, ops, ln, raw))
            self.size[sec] += n

    def directive_size(self, mn, ops, ln):
        if mn == '.word': return 4 * len(ops)
        if mn == '.half': return 2 * len(ops)
        if mn == '.byte': return len(ops)
        if mn == '.space': return self.ev(ops[0], ln, final=False)
        if mn in ('.asciz', '.string'): return len(self.parse_str(ops[0], ln)) + 1
        if mn == '.ascii': return len(self.parse_str(ops[0], ln))
        raise AsmError("line %d: unknown directive %s" % (ln, mn))

    @staticmethod
    def parse_str(s, ln):
        s = s.strip()
        if not (s.startswith('"') and s.endswith('"')):
            raise AsmError("line %d: bad string" % ln)
        return bytes(s[1:-1], 'utf-8').decode('unicode_escape').encode('latin-1')

    def assemble(self, text):
        self.pass1(text)
        text_size = (self.size['text'] + 3) & ~3
        base = {'text': 0, 'data': text_size}
        for name, (sec, off) in self.labels.items():
            self.syms[name] = base[sec] + off
        img = bytearray(text_size + self.size['data'])
        listing = []
        for sec in ('text', 'data'):
            for off, mn, ops, ln, raw in self.items[sec]:
                addr = base[sec] + off
                if mn.startswith('.'):
                    b = self.directive_bytes(mn, ops, ln)
                    img[addr:addr + len(b)] = b
                    listing.append((addr, None, raw.rstrip()))
                    continue
                insts = self.expand(mn, ops, ln)
                for k, (m2, o2) in enumerate(insts):
                    pc = addr + 4 * k
                    w = self.encode(m2, o2, pc, ln)
                    img[pc:pc + 4] = (w & 0xFFFFFFFF).to_bytes(4, 'little')
                    listing.append((pc, w, raw.strip() if k == 0 else '   (cont.) %s %s' % (m2, ', '.join(o2))))
        while len(img) % 4:
            img.append(0)
        return img, listing

    def directive_bytes(self, mn, ops, ln):
        out = bytearray()
        if mn == '.word':
            for o in ops: out += (self.ev(o, ln) & 0xFFFFFFFF).to_bytes(4, 'little')
        elif mn == '.half':
            for o in ops: out += (self.ev(o, ln) & 0xFFFF).to_bytes(2, 'little')
        elif mn == '.byte':
            for o in ops: out.append(self.ev(o, ln) & 0xFF)
        elif mn == '.space':
            out += bytes(self.ev(ops[0], ln))
        elif mn in ('.asciz', '.string'):
            out += self.parse_str(ops[0], ln) + b'\0'
        elif mn == '.ascii':
            out += self.parse_str(ops[0], ln)
        return out


def assemble_file(src, out_prefix, max_words=3072):
    with open(src) as f:
        text = f.read()
    a = Assembler()
    img, lst = a.assemble(text)
    if len(img) // 4 > max_words:
        raise AsmError("program too large (%d words, max %d)" % (len(img) // 4, max_words))
    with open(out_prefix + '.hex', 'w') as f:
        for i in range(0, len(img), 4):
            f.write('%08x\n' % int.from_bytes(img[i:i + 4], 'little'))
    with open(out_prefix + '.lst', 'w') as f:
        for addr, w, txt in lst:
            f.write('%08x  %s  %s\n' % (addr, ('%08x' % w) if w is not None else '        ', txt))
    return img, a


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source')
    ap.add_argument('-o', '--out', help='output prefix (default: source without extension)')
    args = ap.parse_args()
    prefix = args.out or re.sub(r'\.[^.]*$', '', args.source)
    try:
        img, _ = assemble_file(args.source, prefix)
    except AsmError as e:
        sys.exit('assembler error: %s' % e)
    print('%s: %d words -> %s.hex' % (args.source, len(img) // 4, prefix))
