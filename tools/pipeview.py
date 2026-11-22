#!/usr/bin/env python3
"""
pipeview.py - turn the RTL pipeline trace into a readable cycle-by-cycle diagram

  vvp build/cpu_bp1.vvp +PROG=x.hex +OUT=build/x +TRACE
  python3 tools/pipeview.py build/x.trace build/x.lst [--from 1 --to 40]

Each row is one clock cycle; each column shows which instruction occupies that
pipeline stage.  Hazard events (forwarding, load-use stall, mispredict flush)
are annotated on the right.
"""
import argparse

FWD = {0: '', 1: 'EX/MEM', 2: 'MEM/WB'}


def load_listing(path):
    text = {}
    for line in open(path):
        parts = line.rstrip('\n').split(None, 2)
        if len(parts) < 3:
            continue
        try:
            addr = int(parts[0], 16)
            int(parts[1], 16)
        except ValueError:
            continue
        txt = parts[2].strip()
        if txt.startswith('(cont.)'):
            txt = txt[len('(cont.)'):].strip()
            if addr - 4 in text and not text[addr - 4].startswith('?'):
                pass
        text[addr] = txt
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace'); ap.add_argument('listing')
    ap.add_argument('--from', dest='lo', type=int, default=1)
    ap.add_argument('--to', dest='hi', type=int, default=10 ** 9)
    ap.add_argument('--width', type=int, default=21)
    args = ap.parse_args()

    text = load_listing(args.listing)
    w = args.width

    def cell(pc, valid):
        if not valid:
            return '-'.ljust(w)
        t = text.get(int(pc, 16), '(past end: nop)')
        t = ' '.join(t.split('#')[0].split())
        return (t if len(t) <= w else t[:w - 1] + '~').ljust(w)

    hdr = 'cyc  ' + ' | '.join(s.ljust(w) for s in ('IF', 'ID', 'EX', 'MEM', 'WB')) + ' | events'
    print(hdr)
    print('-' * len(hdr))
    for line in open(args.trace):
        f = line.split()
        cyc = int(f[0])
        if cyc < args.lo or cyc > args.hi:
            continue
        pcs = f[1:6]
        valid = f[6]                 # "{WB,MEM,EX,ID,IF}"
        stall, flush, fa, fb = f[7], f[8], int(f[9]), int(f[10])
        cols = []
        for k, stage in enumerate(('IF', 'ID', 'EX', 'MEM', 'WB')):
            v = valid[4 - k] == '1'
            cols.append(cell(pcs[k], v))
        ev = []
        if stall == '1': ev.append('LOAD-USE STALL (hold IF/ID, bubble->EX)')
        if flush == '1': ev.append('MISPREDICT: flush IF+ID, redirect PC')
        if valid[2] == '1':
            if fa: ev.append('fwd rs1<-' + FWD[fa])
            if fb: ev.append('fwd rs2<-' + FWD[fb])
        print('%3d  %s | %s' % (cyc, ' | '.join(cols), ', '.join(ev)))


if __name__ == '__main__':
    main()
