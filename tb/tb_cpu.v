// =============================================================================
// tb_cpu.v : top-level testbench
//
//   vvp sim.vvp +PROG=prog.hex +OUT=prefix [+MAXCYC=n] [+TRACE] [+VCD=file.vcd]
//
//   Runs the program until ECALL retires, then dumps
//     <OUT>.regs   32 lines  - final register file
//     <OUT>.mem    4096 lines - final data memory
//     <OUT>.stats  key value  - performance counters
//     <OUT>.trace  per-cycle pipeline occupancy (with +TRACE)
//   The python regression compares these against the golden ISS.
// =============================================================================
`timescale 1ns/1ps
`ifndef BP_ENABLE
  `define BP_ENABLE 1
`endif
`ifndef BP_INDEX_BITS
  `define BP_INDEX_BITS 5
`endif

module tb_cpu;
    reg clk = 1'b0;
    reg rst = 1'b1;
    wire halted, illegal;

    cpu_top #(.BP_ENABLE(`BP_ENABLE), .BP_INDEX_BITS(`BP_INDEX_BITS)) dut (.clk(clk), .rst(rst), .halted(halted), .illegal(illegal));

    always #5 clk = ~clk;

    integer      maxcyc, i, fd, cyc;
    reg [1023:0] outp, fname;
    reg          trace_en, finished;

    initial begin
        if (!$value$plusargs("MAXCYC=%d", maxcyc)) maxcyc = 2000000;
        if (!$value$plusargs("OUT=%s", outp))      outp   = "sim_out";
        trace_en = $test$plusargs("TRACE");
        finished = 1'b0;
        cyc      = 0;
        if ($value$plusargs("VCD=%s", fname)) begin
            $dumpfile(fname);
            $dumpvars(0, tb_cpu);
        end
        if (trace_en) begin
            $sformat(fname, "%0s.trace", outp);
            fd = $fopen(fname, "w");
        end
        repeat (3) @(posedge clk);
        #1 rst = 1'b0;
    end

    // ---- per-cycle pipeline trace ------------------------------------------
    always @(posedge clk) if (!rst && !finished) begin
        cyc = cyc + 1;
        if (trace_en)
            $fdisplay(fd, "%0d %h %h %h %h %h %b %b %b %0d %0d", cyc,
                dut.core.dbg_pc_if, dut.core.dbg_pc_id, dut.core.dbg_pc_ex,
                dut.core.dbg_pc_mem, dut.core.dbg_pc_wb, dut.core.dbg_valid,
                dut.core.dbg_stall, dut.core.dbg_flush,
                dut.core.dbg_fwd_a, dut.core.dbg_fwd_b);
    end

    // ---- timeout -------------------------------------------------------------
    always @(posedge clk) if (!finished && cyc > maxcyc) begin
        finished = 1'b1;
        $display("RESULT: TIMEOUT after %0d cycles", cyc);
        $finish;
    end

    // ---- completion: dump architectural state -----------------------------------
    initial begin
        wait (rst == 1'b0);
        wait (halted === 1'b1);
        @(posedge clk);          // ECALL retires on this edge (counters update)
        #1;
        finished = 1'b1;

        $sformat(fname, "%0s.regs", outp);
        fd = $fopen(fname, "w");
        for (i = 0; i < 32; i = i + 1) $fdisplay(fd, "%08h", dut.core.u_rf.regs[i]);
        $fclose(fd);

        $sformat(fname, "%0s.mem", outp);
        fd = $fopen(fname, "w");
        for (i = 0; i < 4096; i = i + 1) $fdisplay(fd, "%08h", dut.u_dmem.mem[i]);
        $fclose(fd);

        $sformat(fname, "%0s.stats", outp);
        fd = $fopen(fname, "w");
        $fdisplay(fd, "cycles %0d",     dut.core.cnt_cycles);
        $fdisplay(fd, "instret %0d",    dut.core.cnt_instret);
        $fdisplay(fd, "stalls %0d",     dut.core.cnt_stalls);
        $fdisplay(fd, "flushes %0d",    dut.core.cnt_flushes);
        $fdisplay(fd, "cond_br %0d",    dut.core.cnt_cond_br);
        $fdisplay(fd, "cond_miss %0d",  dut.core.cnt_cond_miss);
        $fdisplay(fd, "jumps %0d",      dut.core.cnt_jumps);
        $fdisplay(fd, "jump_miss %0d",  dut.core.cnt_jump_miss);
        $fclose(fd);

        if (illegal) $display("RESULT: ILLEGAL");
        else         $display("RESULT: HALT");
        $finish;
    end
endmodule
