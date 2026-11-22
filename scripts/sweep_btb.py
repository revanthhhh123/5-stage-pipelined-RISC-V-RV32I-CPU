#!/usr/bin/env python3
"""
sweep_btb.py - design-space exploration: branch-predictor size vs. performance vs. area

For BTB/BHT sizes of 2^k entries (k = 1..6) plus "no predictor":
  * total cycles over the benchmark suite  (RTL simulation)
  * flip-flop count and ~gate-equivalents  (Yosys)
Writes results/btb_sweep.md and docs/btb_sweep.png
"""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)
import regress, synth_report            # noqa: E402

BENCH = ['fib_iter', 'fib_rec', 'bubble_sort', 'matmul4', 'sieve', 'crc32', 'strops']
SIZES = [1, 2, 3, 4, 5, 6]


def total_cycles(bp, idx):
    vvp = 'build/sweep_bp%d_i%d.vvp' % (bp, idx)
    srcs = regress.RTL + ['tb/tb_cpu.v']
    subprocess.run(['iverilog', '-g2012', '-DBP_ENABLE=%d' % bp, '-DBP_INDEX_BITS=%d' % idx, '-I', 'rtl',
                    '-o', vvp] + srcs, check=True)
    tot = 0
    for b in BENCH:
        hexf = 'build/out/%s.hex' % b
        if not os.path.exists(hexf):
            sys.exit('run `make bench` first')
        st, stats = regress.run_rtl(vvp, hexf, 'build/out/%s.sweep' % b)
        assert st == 'HALT'
        tot += stats['cycles']
    return tot


def main():
    rows = []
    base = total_cycles(0, 5)
    s0 = synth_report.run_yosys(0, 'sw_off')
    rows.append(('none', 0, base, s0['flops'], s0['ge']))
    for k in SIZES:
        cyc = total_cycles(1, k)
        sy = synth_report.run_yosys(1, 'sw_%d' % k, k)
        rows.append(('%d' % (1 << k), 1 << k, cyc, sy['flops'], sy['ge']))
        print('entries=%3d cycles=%d flops=%d' % (1 << k, cyc, sy['flops']), flush=True)
    L = ['| BTB/BHT entries | Total cycles | Speed-up vs. no predictor | Flip-flops | ~GE | Area vs. no predictor |',
         '|---:|---:|---:|---:|---:|---:|']
    for name, n, cyc, ff, ge in rows:
        L.append('| %s | %d | %.3fx | %d | %.0f | %+.0f%% |' % (name, cyc, base / cyc, ff, ge, 100 * (ge / rows[0][4] - 1)))
    open('results/btb_sweep.md', 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    try:
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        xs = [r[1] for r in rows[1:]]
        fig, ax1 = plt.subplots(figsize=(7.5, 4))
        ax1.plot(range(len(xs)), [base / r[2] for r in rows[1:]], 'o-', color='#2b6cb0')
        ax1.set_ylabel('speed-up vs. static not-taken', color='#2b6cb0')
        ax1.set_xticks(range(len(xs))); ax1.set_xticklabels(xs); ax1.set_xlabel('BTB / BHT entries')
        ax2 = ax1.twinx()
        ax2.plot(range(len(xs)), [100 * (r[4] / rows[0][4] - 1) for r in rows[1:]], 's--', color='#c53030')
        ax2.set_ylabel('core area increase (%, ~GE)', color='#c53030')
        ax1.set_title('Branch predictor sizing: performance vs. area')
        fig.tight_layout(); fig.savefig('docs/btb_sweep.png', dpi=160)
    except ImportError:
        pass


if __name__ == '__main__':
    main()
