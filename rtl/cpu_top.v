// -----------------------------------------------------------------------------
// cpu_top.v : simulation wrapper = cpu_core + instruction/data memories
// -----------------------------------------------------------------------------
module cpu_top #(
    parameter BP_ENABLE     = 1,
    parameter BP_INDEX_BITS = 5,
    parameter MEM_WORDS     = 4096          // 16 KiB
)(
    input  clk,
    input  rst,
    output halted,
    output illegal
);
    wire [31:0] imem_addr, imem_rdata;
    wire [31:0] dmem_addr, dmem_wdata, dmem_rdata;
    wire [3:0]  dmem_wstrb;
    wire        dmem_re;

    cpu_core #(.BP_ENABLE(BP_ENABLE), .BP_INDEX_BITS(BP_INDEX_BITS)) core (
        .clk(clk), .rst(rst),
        .imem_addr(imem_addr), .imem_rdata(imem_rdata),
        .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata), .dmem_wstrb(dmem_wstrb),
        .dmem_re(dmem_re), .dmem_rdata(dmem_rdata),
        .halted(halted), .illegal_instr(illegal),
        .cnt_cycles(), .cnt_instret(), .cnt_stalls(), .cnt_flushes(),
        .cnt_cond_br(), .cnt_cond_miss(), .cnt_jumps(), .cnt_jump_miss(),
        .dbg_pc_if(), .dbg_pc_id(), .dbg_pc_ex(), .dbg_pc_mem(), .dbg_pc_wb(),
        .dbg_valid(), .dbg_stall(), .dbg_flush(), .dbg_fwd_a(), .dbg_fwd_b()
    );

    imem #(.WORDS(MEM_WORDS)) u_imem (.addr(imem_addr), .rdata(imem_rdata));
    dmem #(.WORDS(MEM_WORDS)) u_dmem (.clk(clk), .addr(dmem_addr), .wdata(dmem_wdata),
                                      .wstrb(dmem_wstrb), .re(dmem_re), .rdata(dmem_rdata));
endmodule
