# =============================================================================
#  5-stage pipelined RISC-V (RV32I) CPU  -  build / verify / synthesize
# =============================================================================
PY      ?= python3
IVERILOG?= iverilog
VVP     ?= vvp
RTL      = $(wildcard rtl/*.v)
BUILD    = build

.PHONY: all test unit directed random bench mutation synth report trace wave clean help

all: test

help:
	@echo "make test       unit tests + directed + 200 random programs (CI target)"
	@echo "make unit       module-level testbenches (ALU, regfile, predictor)"
	@echo "make directed   self-checking ISA tests + benchmarks vs golden ISS"
	@echo "make random     N=400 constrained-random programs vs golden ISS"
	@echo "make bench      CPI table (predictor ON vs OFF)  -> results/"
	@echo "make mutation   inject RTL bugs, check the testbench catches them"
	@echo "make synth      Yosys synthesis + area / logic-depth report"
	@echo "make report     regenerate docs/ plots and tables"
	@echo "make trace P=hazard_demo   pipeline diagram for one program"
	@echo "make wave  P=hazard_demo   dump VCD (open with gtkwave)"

$(BUILD):
	mkdir -p $(BUILD)

unit: | $(BUILD)
	$(IVERILOG) -g2012 -I rtl -o $(BUILD)/tb_alu.vvp rtl/alu.v tb/tb_alu.v
	$(IVERILOG) -g2012 -I rtl -o $(BUILD)/tb_rf.vvp rtl/regfile.v tb/tb_regfile.v
	$(IVERILOG) -g2012 -I rtl -o $(BUILD)/tb_bp.vvp rtl/branch_predictor.v tb/tb_branch_predictor.v
	@$(VVP) -n $(BUILD)/tb_alu.vvp | grep -E "PASS|FAIL|MISMATCH"
	@$(VVP) -n $(BUILD)/tb_rf.vvp  | grep -E "PASS|FAIL"
	@$(VVP) -n $(BUILD)/tb_bp.vvp  | grep -E "PASS|FAIL"

directed: | $(BUILD)
	$(PY) tools/gen_isa_tests.py > /dev/null
	$(PY) scripts/regress.py --suite directed

N ?= 400
random: | $(BUILD)
	$(PY) scripts/regress.py --suite random --n $(N)

test: unit directed
	$(PY) scripts/regress.py --suite random --n 200

bench: | $(BUILD)
	$(PY) scripts/report.py

mutation: | $(BUILD)
	$(PY) scripts/mutation_test.py --random 25

synth:
	yosys -q -l $(BUILD)/yosys.log synth/synth.ys
	@grep -E "Number of cells|Chip area|longest topological path" $(BUILD)/yosys.log | tail -5 || true
	$(PY) scripts/synth_report.py

report: bench synth sweep

sweep: bench
	$(PY) scripts/sweep_btb.py

P ?= hazard_demo
trace: | $(BUILD)
	$(PY) tools/rvasm.py tests/asm/$(P).s -o $(BUILD)/$(P)
	$(IVERILOG) -g2012 -DBP_ENABLE=1 -I rtl -o $(BUILD)/cpu_bp1.vvp $(RTL) tb/tb_cpu.v
	$(VVP) -n $(BUILD)/cpu_bp1.vvp +PROG=$(BUILD)/$(P).hex +OUT=$(BUILD)/$(P) +TRACE
	$(PY) tools/pipeview.py $(BUILD)/$(P).trace $(BUILD)/$(P).lst

wave: | $(BUILD)
	$(PY) tools/rvasm.py tests/asm/$(P).s -o $(BUILD)/$(P)
	$(IVERILOG) -g2012 -DBP_ENABLE=1 -I rtl -o $(BUILD)/cpu_bp1.vvp $(RTL) tb/tb_cpu.v
	$(VVP) -n $(BUILD)/cpu_bp1.vvp +PROG=$(BUILD)/$(P).hex +OUT=$(BUILD)/$(P) +VCD=$(BUILD)/$(P).vcd
	@echo "open with:  gtkwave $(BUILD)/$(P).vcd"

clean:
	rm -rf $(BUILD)/* results/*.json
