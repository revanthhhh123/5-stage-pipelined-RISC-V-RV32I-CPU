#!/usr/bin/env python3
"""
report.py - run the benchmark programs with the dynamic branch predictor ON and
OFF and produce results/benchmarks.{json,md} and docs/cpi.png.

Also verifies the cycle-accounting identity that must hold for this pipeline:

    cycles = instret + 4 (pipeline fill) + load-use stalls + 2 * mispredict flushes
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import regress  # noqa: E402

BENCH = ['fib_iter', 'fib_rec', 'bubble_sort', 'matmul4', 'sieve', 'crc32', 'strops']


def main():
    os.makedirs(os.path.join(ROOT, 'results'), exist_ok=True)
    os.makedirs(os.path.join(ROOT, 'docs'), exist_ok=True)
    rows = []
    for name in BENCH:
        src = os.path.join(ROOT, 'tests', 'asm', name + '.s')
        r = regress.run_one(src, name, [0, 1])
        if not r['ok']:
            sys.exit('benchmark %s FAILED: %s' % (name, r['msgs']))
        row = {'name': name, 'instret': r['instret']}
        for bp in (0, 1):
            s = r['bp'][bp]
            ident = s['instret'] + 4 + s['stalls'] + 2 * s['flushes']
            if ident != s['cycles']:
                sys.exit('accounting identity broken for %s bp%d: %d != %d' % (name, bp, ident, s['cycles']))
            row['bp%d' % bp] = dict(s, cpi=s['cycles'] / s['instret'])
        rows.append(row)
    json.dump(rows, open(os.path.join(ROOT, 'results', 'benchmarks.json'), 'w'), indent=1)

    L = ['| Benchmark | Instr. | Cycles (no BP) | CPI (no BP) | Cycles (BTB+BHT) | CPI (BTB+BHT) | Speed-up | Load-use stalls | Cond-branch accuracy (BP) |',
         '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    tot0 = tot1 = toti = 0
    for r in rows:
        a, b = r['bp0'], r['bp1']
        acc = 100.0 * (1 - b['cond_miss'] / b['cond_br']) if b['cond_br'] else 100.0
        L.append('| `%s` | %d | %d | %.3f | %d | %.3f | %.2fx | %d | %.1f%% |' % (
            r['name'], r['instret'], a['cycles'], a['cpi'], b['cycles'], b['cpi'],
            a['cycles'] / b['cycles'], b['stalls'], acc))
        tot0 += a['cycles']; tot1 += b['cycles']; toti += r['instret']
    L.append('| **total** | %d | %d | %.3f | %d | %.3f | %.2fx | | |' % (toti, tot0, tot0 / toti, tot1, tot1 / toti, tot0 / tot1))
    open(os.path.join(ROOT, 'results', 'benchmarks.md'), 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        names = [r['name'] for r in rows]
        x = np.arange(len(names)); w = 0.38
        fig, ax = plt.subplots(figsize=(9, 4.2))
        b0 = ax.bar(x - w / 2, [r['bp0']['cpi'] for r in rows], w, label='static not-taken', color='#b9c4d4')
        b1 = ax.bar(x + w / 2, [r['bp1']['cpi'] for r in rows], w, label='BTB + 2-bit BHT', color='#2b6cb0')
        ax.axhline(1.0, color='k', lw=0.8, ls='--'); ax.text(len(names) - 0.5, 1.005, 'ideal CPI = 1', ha='right', va='bottom', fontsize=8)
        for bars in (b0, b1):
            for b in bars:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, '%.2f' % b.get_height(), ha='center', fontsize=7)
        ax.set_xticks(x); ax.set_xticklabels(names, rotation=20); ax.set_ylabel('cycles per instruction')
        ax.set_title('CPI of the 5-stage RV32I core: effect of dynamic branch prediction')
        ax.set_ylim(0.95, max(r['bp0']['cpi'] for r in rows) * 1.08); ax.legend(frameon=False)
        fig.tight_layout(); fig.savefig(os.path.join(ROOT, 'docs', 'cpi.png'), dpi=160)

        fig, ax = plt.subplots(figsize=(9, 3.6))
        bottoms = np.zeros(len(rows))
        parts = [('useful (1.0)', [1.0] * len(rows), '#2b6cb0'),
                 ('pipeline fill', [4.0 / r['instret'] for r in rows], '#9aa5b1'),
                 ('load-use stalls', [r['bp1']['stalls'] / r['instret'] for r in rows], '#dd6b20'),
                 ('mispredict flushes', [2 * r['bp1']['flushes'] / r['instret'] for r in rows], '#c53030')]
        for lab, vals, col in parts:
            ax.bar(names, vals, bottom=bottoms, label=lab, color=col); bottoms += np.array(vals)
        ax.set_ylabel('cycles per instruction'); ax.set_title('Where the cycles go (with branch predictor)')
        plt.setp(ax.get_xticklabels(), rotation=20); ax.legend(frameon=False, fontsize=8, ncol=2)
        fig.tight_layout(); fig.savefig(os.path.join(ROOT, 'docs', 'cpi_breakdown.png'), dpi=160)
        print('wrote docs/cpi.png, docs/cpi_breakdown.png')
    except ImportError:
        print('matplotlib not available - skipping plots')


if __name__ == '__main__':
    main()
