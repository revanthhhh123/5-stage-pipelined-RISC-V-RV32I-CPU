#!/usr/bin/env python3
"""
mutation_test.py - "who tests the tests?"

Injects one bug at a time into a copy of the RTL and checks that the
regression suite FAILS ("mutant killed").  A mutant that survives would mean
the verification environment has a blind spot.

usage: mutation_test.py [--random N]
"""
import argparse, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUTANTS = [
 # name, file, old, new
 ('no EX/MEM forwarding (rs1)',      'forwarding_unit.v', '(mem_we && mem_rd != 5\'d0 && mem_rd == ex_rs1)', '(1\'b0)'),
 ('no EX/MEM forwarding (rs2)',      'forwarding_unit.v', '(mem_we && mem_rd != 5\'d0 && mem_rd == ex_rs2)', '(1\'b0)'),
 ('no MEM/WB forwarding (rs1)',      'forwarding_unit.v', '(wb_we  && wb_rd  != 5\'d0 && wb_rd  == ex_rs1)', '(1\'b0)'),
 ('no MEM/WB forwarding (rs2)',      'forwarding_unit.v', '(wb_we  && wb_rd  != 5\'d0 && wb_rd  == ex_rs2)', '(1\'b0)'),
 ('forward priority swapped',        'forwarding_unit.v', "(mem_we && mem_rd != 5'd0 && mem_rd == ex_rs1) ? 2'b01 :\n                   (wb_we  && wb_rd  != 5'd0 && wb_rd  == ex_rs1) ? 2'b10 : 2'b00;",
                                                          "(wb_we  && wb_rd  != 5'd0 && wb_rd  == ex_rs1) ? 2'b10 :\n                   (mem_we && mem_rd != 5'd0 && mem_rd == ex_rs1) ? 2'b01 : 2'b00;"),
 ('forwarding from x0 allowed',      'forwarding_unit.v', "mem_we && mem_rd != 5'd0 && mem_rd == ex_rs2", "mem_we && mem_rd == ex_rs2"),
 ('load-use stall removed',          'hazard_unit.v',     'assign load_use_stall = id_valid && ex_is_load', 'assign load_use_stall = 1\'b0 && ex_is_load'),
 ('load-use ignores rs2',            'hazard_unit.v',     '(id_uses_rs2 && ex_rd == id_rs2)', '1\'b0'),
 ('regfile write-through removed',   'regfile.v',         '(we && waddr == raddr1)    ? wdata : regs[raddr1]', 'regs[raddr1]'),
 ('x0 writable',                     'regfile.v',         'if (we && (waddr != 5\'d0)) regs', 'if (we) regs'),
 ('BNE behaves like BEQ',            'cpu_core.v',        "3'b001:  cond = ~eq;", "3'b001:  cond = eq;"),
 ('BLT signed->unsigned',            'cpu_core.v',        "3'b100:  cond = lt;", "3'b100:  cond = ltu;"),
 ('BGEU uses signed compare',        'cpu_core.v',        "3'b111:  cond = ~ltu;", "3'b111:  cond = ~lt;"),
 ('JALR bit0 not cleared',           'cpu_core.v',        '{alu_y[31:1], 1\'b0}', 'alu_y'),
 ('JAL/JALR link = pc (not pc+4)',   'cpu_core.v',        'ex_link ? ex_pc_plus4 : alu_y', 'ex_link ? ex_pc : alu_y'),
 ('mispredict ignores wrong target', 'cpu_core.v',        '(actual_taken && (ex_pred_target != actual_target))', '1\'b0'),
 ('mispredict never flushes ID',     'cpu_core.v',        'wire id_bubble = redirect | stall;', 'wire id_bubble = stall;'),
 ('wrong-path fetch not squashed',   'cpu_core.v',        'if (rst || redirect) begin\n            if_id_valid', 'if (rst) begin\n            if_id_valid'),
 ('no squash after ECALL',           'cpu_core.v',        'if (stop_fetch || halt_in_id) begin', 'if (1\'b0) begin'),
 ('LB not sign extended',            'cpu_core.v',        "{{24{ld_shift[7]}},  ld_shift[7:0]}", "{24'b0, ld_shift[7:0]}"),
 ('LH not sign extended',            'cpu_core.v',        "{{16{ld_shift[15]}}, ld_shift[15:0]}", "{16'b0, ld_shift[15:0]}"),
 ('SB writes wrong lane',            'cpu_core.v',        "4'b0001 << mem_result[1:0]", "4'b0001"),
 ('SH always low half',              'cpu_core.v',        "4'b0011 << {mem_result[1], 1'b0}", "4'b0011"),
 ('load byte-lane shift removed',    'cpu_core.v',        'dmem_rdata >> {mem_result[1:0], 3\'b000}', 'dmem_rdata'),
 ('store data from stale rs2',       'cpu_core.v',        'mem_rs2       <= ex_rs2_fwd;', 'mem_rs2       <= ex_rs2_val;'),
 ('SRA acts as SRL',                 'alu.v',             '$signed(a) >>> b[4:0]', 'a >> b[4:0]'),
 ('SLT unsigned',                    'alu.v',             '($signed(a) < $signed(b))', '(a < b)'),
 ('SUB acts as ADD',                 'alu.v',             'y = a - b;', 'y = a + b;'),
 ('shift amount uses 6 bits',        'alu.v',             'a << b[4:0]', 'a << b[5:0]'),
 ('SRAI/SRLI funct7 ignored',        'control_unit.v',    "3'b101: f3_to_alu = f7_5 ? `ALU_SRA : `ALU_SRL;", "3'b101: f3_to_alu = `ALU_SRL;"),
 ('OP-IMM treats f7 as SUB',         'control_unit.v',    "(is_reg & f7_5) ? `ALU_SUB", "(f7_5) ? `ALU_SUB"),
 ('AUIPC uses rs1',                  'control_unit.v',    'alu_src_imm = 1; a_sel_pc = 1; end', 'alu_src_imm = 1; end'),
 ('B-type imm bit 11 wrong',         'imm_gen.v',         '{{19{instr[31]}}, instr[31], instr[7],', '{{19{instr[31]}}, instr[31], instr[20],'),
 ('J-type imm bit order wrong',      'imm_gen.v',         'instr[20], instr[30:21], 1\'b0};  ', 'instr[21], instr[30:22], instr[20], 1\'b0};  '),
 ('S-type imm low bits wrong',       'imm_gen.v',         '{{20{instr[31]}}, instr[31:25], instr[11:7]}', '{{20{instr[31]}}, instr[31:25], instr[24:20]}'),
]


def run(args_extra, env):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'regress.py')] + args_extra,
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout


def eval_mutant(i, item, n_random):
    name, fname, old, new = item
    d = os.path.join(BASE, 'm%02d' % i)
    shutil.copytree(os.path.join(ROOT, 'rtl'), os.path.join(d, 'rtl'))
    p = os.path.join(d, 'rtl', fname)
    src = open(p).read()
    if old not in src:
        shutil.rmtree(d, ignore_errors=True)
        return name, 'skip', fname
    open(p, 'w').write(src.replace(old, new, 1))
    env = dict(os.environ, RTL_DIR=os.path.join(d, 'rtl'), BUILD_DIR=os.path.join(d, 'build'))
    os.makedirs(env['BUILD_DIR'], exist_ok=True)
    rc, out = run(['--suite', 'directed', '--bp', '1'], env)
    how = 'directed'
    if rc == 0 and n_random:
        rc, out = run(['--suite', 'random', '--n', str(n_random), '--bp', '1'], env)
        how = 'random'
    shutil.rmtree(d, ignore_errors=True)
    return name, ('killed' if rc != 0 else 'survived'), how


BASE = os.path.join(ROOT, 'build', 'mutants')


def main():
    from concurrent.futures import ThreadPoolExecutor
    ap = argparse.ArgumentParser()
    ap.add_argument('--random', type=int, default=30)
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    shutil.rmtree(BASE, ignore_errors=True)
    os.makedirs(BASE)
    with ThreadPoolExecutor(args.jobs) as ex:
        futs = [ex.submit(eval_mutant, i, m, args.random) for i, m in enumerate(MUTANTS)]
        results = []
        for f in futs:
            name, status, how = f.result()
            results.append((name, status, how))
            tag = {'killed': 'KILLED  by %-8s' % how, 'survived': 'SURVIVED         ', 'skip': 'skip (%s)    ' % how}[status]
            print('  [%s] %s' % (tag, name), flush=True)
    killed = sum(1 for r in results if r[1] == 'killed')
    survivors = [r[0] for r in results if r[1] != 'killed']
    print('\nmutation score: %d / %d mutants killed' % (killed, len(MUTANTS)))
    if survivors:
        print('survivors:', *survivors, sep='\n  - ')
    sys.exit(0 if not survivors else 1)


if __name__ == '__main__':
    main()
