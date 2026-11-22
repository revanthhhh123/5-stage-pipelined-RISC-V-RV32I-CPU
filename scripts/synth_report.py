#!/usr/bin/env python3
"""
synth_report.py - run Yosys for the default core and for a variant without the
branch predictor, then write results/synth.md with a compact summary.

Gate-equivalent (GE) weights are a ROUGH rule of thumb for a generic CMOS
library (NAND2 = 1 GE); they are only meant for relative comparisons.
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
FILES = ['alu', 'regfile', 'imm_gen', 'control_unit', 'forwarding_unit', 'hazard_unit',
         'branch_predictor', 'cpu_core']
GE = {'$_NOT_': 0.5, '$_AND_': 1.5, '$_OR_': 1.5, '$_NAND_': 1.0, '$_NOR_': 1.0,
      '$_XOR_': 2.5, '$_XNOR_': 2.5, '$_MUX_': 2.5, '$_DFF_P_': 6.0, '$_SDFF_PP0_': 7.0,
      '$_DFFE_PP_': 7.0, '$_SDFFE_PP0P_': 8.0, '$_SDFFCE_PP0P_': 8.0, '$_DFFE_PP0P_': 8.0,
      '$_SDFFE_PP0N_': 8.0}


def run_yosys(bp, tag, idx=5):
    srcs = ' '.join('rtl/%s.v' % f for f in FILES)
    cmds = ['read_verilog -DSYNTHESIS -I rtl %s' % srcs,
            'chparam -set BP_ENABLE %d -set BP_INDEX_BITS %d cpu_core' % (bp, idx),
            'hierarchy -check -top cpu_core',
            'synth -top cpu_core -flatten',
            'abc -g AND,NAND,OR,NOR,XOR,XNOR,MUX',
            'opt_clean',
            'tee -o build/ltp_%s.txt ltp -noff' % tag,
            'tee -o build/stat_%s.txt stat' % tag]
    r = subprocess.run(['yosys', '-q', '-p', '; '.join(cmds)], capture_output=True, text=True)
    if r.returncode:
        sys.exit('yosys failed:\n' + r.stdout + r.stderr)
    stat = open('build/stat_%s.txt' % tag).read()
    ltp = open('build/ltp_%s.txt' % tag).read()
    cells = {}
    for m in re.finditer(r'^\s+(\d+)\s+(?:[\d.]+\s+)?(\$_\w+_)\s*$', stat, re.M):
        cells[m.group(2)] = cells.get(m.group(2), 0) + int(m.group(1))
    if not cells:
        for m in re.finditer(r'^\s+(\$_\w+_)\s+(\d+)\s*$', stat, re.M):
            cells[m.group(1)] = int(m.group(2))
    depth = re.search(r'Longest topological path.*?\(length=(\d+)\)', ltp)
    total = sum(cells.values())
    ffs = sum(v for k, v in cells.items() if 'DFF' in k)
    ge = sum(GE.get(k, 1.5) * v for k, v in cells.items())
    return {'cells': total, 'flops': ffs, 'comb': total - ffs, 'ge': ge,
            'depth': int(depth.group(1)) if depth else -1, 'by_type': cells}


def main():
    os.makedirs('build', exist_ok=True); os.makedirs('results', exist_ok=True)
    with_bp = run_yosys(1, 'bp1')
    no_bp = run_yosys(0, 'bp0')
    lines = ['# Synthesis summary (Yosys, generic gates, no technology library)', '',
             '| Configuration | Total cells | Flip-flops | Comb. gates | ~Gate equivalents | Logic depth (gate levels) |',
             '|---|---:|---:|---:|---:|---:|']
    for n, d in (('Core + BTB/BHT predictor (default)', with_bp), ('Core, static not-taken (no predictor)', no_bp)):
        lines.append('| %s | %d | %d | %d | %.0f | %d |' % (n, d['cells'], d['flops'], d['comb'], d['ge'], d['depth']))
    lines += ['', 'Predictor cost: **+%d flip-flops, +%.0f GE (%.0f%%)**.' % (
        with_bp['flops'] - no_bp['flops'], with_bp['ge'] - no_bp['ge'],
        100.0 * (with_bp['ge'] - no_bp['ge']) / max(no_bp['ge'], 1)), '',
        'Cell-type breakdown (default configuration):', '', '| Cell | Count |', '|---|---:|']
    for k, v in sorted(with_bp['by_type'].items(), key=lambda kv: -kv[1]):
        lines.append('| `%s` | %d |' % (k, v))
    open('results/synth.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:8]))


if __name__ == '__main__':
    main()
