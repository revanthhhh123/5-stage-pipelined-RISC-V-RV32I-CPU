#!/usr/bin/env python3
"""
regress.py - regression driver

For every test program:
  1. assemble with tools/rvasm.py
  2. run the golden ISS (tools/rviss.py)
  3. run the RTL (Icarus Verilog) for each predictor configuration
  4. compare   registers, full data memory and retired-instruction count
  5. check the '# CHECK xN value' self-checks written in the .s file
     (expected values computed independently of both models)

usage:
  regress.py --suite directed        # tests/asm + tests/generated
  regress.py --suite random --n 200  # random programs
  regress.py --suite all
"""
import argparse, glob, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import rvasm, rviss                      # noqa: E402

BUILD = os.environ.get('BUILD_DIR', os.path.join(ROOT, 'build'))
OUT = os.path.join(BUILD, 'out')
RTL_DIR = os.environ.get('RTL_DIR', os.path.join(ROOT, 'rtl'))
RTL = sorted(glob.glob(os.path.join(RTL_DIR, '*.v')))


def compile_rtl(bp):
    vvp = os.path.join(BUILD, 'cpu_bp%d.vvp' % bp)
    srcs = RTL + [os.path.join(ROOT, 'tb', 'tb_cpu.v')]
    newest = max(os.path.getmtime(s) for s in srcs)
    if os.path.exists(vvp) and os.path.getmtime(vvp) > newest:
        return vvp
    cmd = ['iverilog', '-g2012', '-DBP_ENABLE=%d' % bp, '-I', RTL_DIR, '-o', vvp] + srcs
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit('iverilog failed:\n' + r.stderr)
    return vvp


def run_rtl(vvp, hexf, prefix, maxcyc=3000000, extra=()):
    cmd = ['vvp', '-n', vvp, '+PROG=' + hexf, '+OUT=' + prefix, '+MAXCYC=%d' % maxcyc] + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    m = re.search(r'RESULT: (\w+)', r.stdout)
    status = m.group(1) if m else 'NORESULT'
    stats = {}
    if os.path.exists(prefix + '.stats'):
        for l in open(prefix + '.stats'):
            k, v = l.split()
            stats[k] = int(v)
    return status, stats


def parse_checks(src):
    chk = []
    for l in open(src):
        m = re.match(r'\s*#\s*CHECK\s+x(\d+)\s+(\S+)', l)
        if m:
            chk.append((int(m.group(1)), int(m.group(2), 0) & 0xFFFFFFFF))
    return chk


def run_one(src, name, bps, keep_trace=False):
    """returns dict(name, ok, instret, per-bp stats, messages)"""
    os.makedirs(OUT, exist_ok=True)
    pre = os.path.join(OUT, name)
    res = {'name': name, 'ok': True, 'msgs': [], 'bp': {}}
    try:
        img, _ = rvasm.assemble_file(src, pre)
    except rvasm.AsmError as e:
        res['ok'] = False; res['msgs'].append('assembler: %s' % e); return res

    iss = rviss.ISS(rviss.read_hex(pre + '.hex'))
    try:
        res['instret'] = iss.run(max_steps=3_000_000)
    except rviss.SimError as e:
        res['ok'] = False; res['msgs'].append('ISS: %s' % e); return res
    open(pre + '.iss.regs', 'w').write(iss.regs_text())
    open(pre + '.iss.mem', 'w').write(iss.mem_text())
    res['iss_branches'] = iss.branches
    res['iss_taken'] = iss.taken

    for k, v in parse_checks(src):
        if iss.x[k] != v:
            res['ok'] = False
            res['msgs'].append('self-check x%d = %#x, expected %#x' % (k, iss.x[k], v))

    for bp in bps:
        vvp = compile_rtl(bp)
        p = '%s.bp%d' % (pre, bp)
        status, stats = run_rtl(vvp, pre + '.hex', p, maxcyc=6 * res['instret'] + 2000)
        res['bp'][bp] = stats
        if status != 'HALT':
            res['ok'] = False; res['msgs'].append('bp%d: RTL status %s' % (bp, status)); continue
        if open(p + '.regs').read() != open(pre + '.iss.regs').read():
            res['ok'] = False
            a = open(p + '.regs').read().split(); b = open(pre + '.iss.regs').read().split()
            diffs = ['x%d rtl=%s iss=%s' % (i, a[i], b[i]) for i in range(32) if a[i] != b[i]]
            res['msgs'].append('bp%d: register mismatch: %s' % (bp, '; '.join(diffs[:4])))
        if open(p + '.mem').read() != open(pre + '.iss.mem').read():
            res['ok'] = False; res['msgs'].append('bp%d: data memory mismatch' % bp)
        if stats.get('instret') != res['instret']:
            res['ok'] = False
            res['msgs'].append('bp%d: instret rtl=%s iss=%s' % (bp, stats.get('instret'), res['instret']))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=['directed', 'random', 'all', 'bench'], default='directed')
    ap.add_argument('--n', type=int, default=100, help='number of random programs')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--bp', choices=['0', '1', 'both'], default='both')
    ap.add_argument('--json', help='write results to this json file')
    args = ap.parse_args()
    bps = [0, 1] if args.bp == 'both' else [int(args.bp)]
    os.makedirs(BUILD, exist_ok=True)

    tests = []
    if args.suite in ('directed', 'all', 'bench'):
        for s in sorted(glob.glob(os.path.join(ROOT, 'tests', 'asm', '*.s'))):
            tests.append((s, os.path.basename(s)[:-2]))
    if args.suite in ('directed', 'all'):
        for s in sorted(glob.glob(os.path.join(ROOT, 'tests', 'generated', '*.s'))):
            tests.append((s, os.path.basename(s)[:-2]))
    if args.suite in ('random', 'all'):
        import gen_random
        rdir = os.path.join(BUILD, 'random'); os.makedirs(rdir, exist_ok=True)
        for i in range(args.n):
            seed = args.seed * 100000 + i
            f = os.path.join(rdir, 'rand_%05d.s' % seed)
            gen_random.generate(seed, f)
            tests.append((f, 'rand_%05d' % seed))

    t0 = time.time(); passed = 0; results = []
    print('%-22s %8s %8s %6s   %s' % ('test', 'instret', 'cyc(bp1)' if 1 in bps else 'cyc', 'CPI', 'status'))
    for src, name in tests:
        r = run_one(src, name, bps)
        results.append(r)
        passed += r['ok']
        st = r['bp'].get(1) or r['bp'].get(0) or {}
        cpi = (st.get('cycles', 0) / r['instret']) if r.get('instret') and st else 0
        line = '%-22s %8s %8s %6.3f   %s' % (name, r.get('instret', '-'), st.get('cycles', '-'), cpi,
                                             'PASS' if r['ok'] else 'FAIL')
        if args.suite != 'random' or not r['ok'] or len(tests) <= 20:
            print(line)
        for m in r['msgs']:
            print('      !', m)
    print('-' * 60)
    print('%d / %d passed   (%.1fs)' % (passed, len(tests), time.time() - t0))
    if args.json:
        json.dump(results, open(args.json, 'w'), indent=1)
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == '__main__':
    main()
