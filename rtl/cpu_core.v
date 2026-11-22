// =============================================================================
// cpu_core.v : 5-stage pipelined RV32I processor core (synthesizable)
//
//   IF  -> ID  -> EX  -> MEM -> WB
//
//   Hazard handling
//   ---------------
//   * RAW data hazards ........ full forwarding  EX/MEM->EX and MEM/WB->EX,
//                               plus write-through register file (WB->ID)
//   * Load-use hazard ......... 1-cycle stall (PC/IF-ID frozen, bubble to EX)
//   * Control hazards ......... dynamic prediction in IF (BTB + 2-bit BHT);
//                               branches/jumps are resolved in EX; a wrong
//                               prediction flushes IF and ID (2-cycle penalty)
//   * ECALL/EBREAK ............ younger instructions are squashed, the core
//                               drains and raises `halted` when the ECALL
//                               reaches WB (precise stop, used by testbench)
//
//   Memory interface: Harvard style, combinational (async) read ports and a
//   byte-strobed synchronous write port, so the core is memory-technology
//   independent (SRAM macro / FPGA BRAM wrappers can be added outside).
// =============================================================================
`include "riscv_defs.vh"

module cpu_core #(
    parameter BP_ENABLE     = 1,
    parameter BP_INDEX_BITS = 5,
    parameter RESET_PC      = 32'h0000_0000
)(
    input         clk,
    input         rst,

    // instruction memory
    output [31:0] imem_addr,
    input  [31:0] imem_rdata,

    // data memory
    output [31:0] dmem_addr,
    output [31:0] dmem_wdata,
    output [3:0]  dmem_wstrb,
    output        dmem_re,
    input  [31:0] dmem_rdata,

    // status
    output        halted,           // ECALL/EBREAK has reached WB
    output        illegal_instr,    // halted because of an illegal opcode

    // performance counters (frozen after halt)
    output reg [31:0] cnt_cycles,
    output reg [31:0] cnt_instret,
    output reg [31:0] cnt_stalls,      // load-use stall cycles
    output reg [31:0] cnt_flushes,     // mispredict flush events
    output reg [31:0] cnt_cond_br,     // conditional branches executed
    output reg [31:0] cnt_cond_miss,   // ... of which mispredicted
    output reg [31:0] cnt_jumps,       // JAL + JALR executed
    output reg [31:0] cnt_jump_miss,   // ... of which mispredicted

    // debug / trace
    output [31:0] dbg_pc_if,
    output [31:0] dbg_pc_id,
    output [31:0] dbg_pc_ex,
    output [31:0] dbg_pc_mem,
    output [31:0] dbg_pc_wb,
    output [4:0]  dbg_valid,        // {WB,MEM,EX,ID,IF}
    output        dbg_stall,
    output        dbg_flush,
    output [1:0]  dbg_fwd_a,
    output [1:0]  dbg_fwd_b
);
    localparam [31:0] NOP = 32'h0000_0013;      // addi x0,x0,0

    // -------------------------------------------------------------------------
    // Forward declarations
    // -------------------------------------------------------------------------
    wire        stall;                  // load-use stall
    wire        redirect;               // EX-stage misprediction
    wire [31:0] redirect_pc;

    // =========================================================================
    // IF stage
    // =========================================================================
    reg  [31:0] pc;
    wire [31:0] pc_plus4 = pc + 32'd4;
    wire        pred_taken;
    wire [31:0] pred_target;

    // predictor update port (driven from EX)
    wire        bp_upd_en;
    wire [31:0] ex_pc_w;
    wire        ex_is_branch_w;
    wire        actual_taken;
    wire [31:0] actual_target;

    branch_predictor #(.ENABLE(BP_ENABLE), .INDEX_BITS(BP_INDEX_BITS)) u_bp (
        .clk(clk), .rst(rst),
        .pc(pc), .pred_taken(pred_taken), .pred_target(pred_target),
        .upd_en(bp_upd_en), .upd_pc(ex_pc_w), .upd_is_cond(ex_is_branch_w),
        .upd_taken(actual_taken), .upd_target(actual_target)
    );

    assign imem_addr = pc;

    always @(posedge clk) begin
        if (rst)             pc <= RESET_PC;
        else if (redirect)   pc <= redirect_pc;
        else if (!stall)     pc <= pred_taken ? pred_target : pc_plus4;
    end

    // =========================================================================
    // IF/ID pipeline register
    // =========================================================================
    reg         if_id_valid;
    reg  [31:0] if_id_pc;
    reg  [31:0] if_id_instr;
    reg         if_id_pred_taken;
    reg  [31:0] if_id_pred_target;
    reg         stop_fetch;             // an ECALL is in flight: stop feeding the pipe
    wire        halt_in_id;

    always @(posedge clk) begin
        if (rst || redirect) begin
            if_id_valid       <= 1'b0;
            if_id_pc          <= 32'b0;
            if_id_instr       <= NOP;
            if_id_pred_taken  <= 1'b0;
            if_id_pred_target <= 32'b0;
        end else if (!stall) begin
            if (stop_fetch || halt_in_id) begin
                if_id_valid       <= 1'b0;
                if_id_pc          <= 32'b0;
                if_id_instr       <= NOP;
                if_id_pred_taken  <= 1'b0;
                if_id_pred_target <= 32'b0;
            end else begin
                if_id_valid       <= 1'b1;
                if_id_pc          <= pc;
                if_id_instr       <= imem_rdata;
                if_id_pred_taken  <= pred_taken;
                if_id_pred_target <= pred_target;
            end
        end
    end

    always @(posedge clk) begin
        if (rst || redirect) stop_fetch <= 1'b0;
        else if (halt_in_id) stop_fetch <= 1'b1;
    end

    // =========================================================================
    // ID stage
    // =========================================================================
    wire [4:0] id_rd  = if_id_instr[11:7];
    wire [4:0] id_rs1 = if_id_instr[19:15];
    wire [4:0] id_rs2 = if_id_instr[24:20];

    wire        c_reg_write, c_mem_read, c_mem_write, c_alu_src_imm, c_a_sel_pc;
    wire        c_is_branch, c_is_jal, c_is_jalr, c_link, c_halt, c_illegal;
    wire        c_uses_rs1, c_uses_rs2;
    wire [3:0]  c_alu_op;

    control_unit u_ctrl (
        .opcode(if_id_instr[6:0]), .funct3(if_id_instr[14:12]), .funct7_5(if_id_instr[30]),
        .reg_write(c_reg_write), .mem_read(c_mem_read), .mem_write(c_mem_write),
        .alu_src_imm(c_alu_src_imm), .a_sel_pc(c_a_sel_pc),
        .is_branch(c_is_branch), .is_jal(c_is_jal), .is_jalr(c_is_jalr),
        .link(c_link), .halt(c_halt), .illegal(c_illegal),
        .uses_rs1(c_uses_rs1), .uses_rs2(c_uses_rs2), .alu_op(c_alu_op)
    );

    assign halt_in_id = if_id_valid & c_halt;

    wire [31:0] id_imm;
    imm_gen u_imm (.instr(if_id_instr), .imm(id_imm));

    // write-back signals (declared here, driven in WB section)
    wire        wb_we;
    wire [4:0]  wb_rd_w;
    wire [31:0] wb_data_w;

    wire [31:0] rf_rdata1, rf_rdata2;
    regfile u_rf (
        .clk(clk), .we(wb_we), .waddr(wb_rd_w), .wdata(wb_data_w),
        .raddr1(id_rs1), .raddr2(id_rs2), .rdata1(rf_rdata1), .rdata2(rf_rdata2)
    );

    // ---- load-use hazard detection -----------------------------------------
    wire        ex_is_load_w;
    wire [4:0]  ex_rd_w;
    hazard_unit u_haz (
        .id_valid(if_id_valid), .id_uses_rs1(c_uses_rs1), .id_uses_rs2(c_uses_rs2),
        .id_rs1(id_rs1), .id_rs2(id_rs2),
        .ex_is_load(ex_is_load_w), .ex_rd(ex_rd_w),
        .load_use_stall(stall)
    );

    // =========================================================================
    // ID/EX pipeline register   (bubble on redirect or load-use stall)
    // =========================================================================
    wire id_bubble = redirect | stall;

    reg         ex_valid;
    reg  [31:0] ex_pc, ex_rs1_val, ex_rs2_val, ex_imm;
    reg  [4:0]  ex_rs1, ex_rs2, ex_rd;
    reg  [2:0]  ex_funct3;
    reg  [3:0]  ex_alu_op;
    reg         ex_reg_write, ex_is_load, ex_is_store, ex_alu_src_imm, ex_a_sel_pc;
    reg         ex_is_branch, ex_is_jal, ex_is_jalr, ex_link, ex_halt, ex_illegal;
    reg         ex_pred_taken;
    reg  [31:0] ex_pred_target;

    always @(posedge clk) begin
        if (rst || id_bubble) begin
            ex_valid <= 1'b0;      ex_pc <= 32'b0;       ex_rs1_val <= 32'b0;
            ex_rs2_val <= 32'b0;   ex_imm <= 32'b0;      ex_rs1 <= 5'b0;
            ex_rs2 <= 5'b0;        ex_rd <= 5'b0;        ex_funct3 <= 3'b0;
            ex_alu_op <= `ALU_ADD; ex_reg_write <= 1'b0; ex_is_load <= 1'b0;
            ex_is_store <= 1'b0;   ex_alu_src_imm <= 1'b0; ex_a_sel_pc <= 1'b0;
            ex_is_branch <= 1'b0;  ex_is_jal <= 1'b0;   ex_is_jalr <= 1'b0;
            ex_link <= 1'b0;       ex_halt <= 1'b0;      ex_illegal <= 1'b0;
            ex_pred_taken <= 1'b0; ex_pred_target <= 32'b0;
        end else begin
            ex_valid       <= if_id_valid;
            ex_pc          <= if_id_pc;
            ex_rs1_val     <= rf_rdata1;
            ex_rs2_val     <= rf_rdata2;
            ex_imm         <= id_imm;
            ex_rs1         <= id_rs1;
            ex_rs2         <= id_rs2;
            ex_rd          <= id_rd;
            ex_funct3      <= if_id_instr[14:12];
            ex_alu_op      <= c_alu_op;
            ex_reg_write   <= c_reg_write & if_id_valid;
            ex_is_load     <= c_mem_read  & if_id_valid;
            ex_is_store    <= c_mem_write & if_id_valid;
            ex_alu_src_imm <= c_alu_src_imm;
            ex_a_sel_pc    <= c_a_sel_pc;
            ex_is_branch   <= c_is_branch & if_id_valid;
            ex_is_jal      <= c_is_jal    & if_id_valid;
            ex_is_jalr     <= c_is_jalr   & if_id_valid;
            ex_link        <= c_link;
            ex_halt        <= c_halt      & if_id_valid;
            ex_illegal     <= c_illegal   & if_id_valid;
            ex_pred_taken  <= if_id_pred_taken;
            ex_pred_target <= if_id_pred_target;
        end
    end

    assign ex_is_load_w = ex_is_load;
    assign ex_rd_w      = ex_rd;

    // =========================================================================
    // EX stage
    // =========================================================================
    reg         mem_valid;
    reg  [31:0] mem_pc, mem_result, mem_rs2;
    reg  [4:0]  mem_rd;
    reg  [2:0]  mem_funct3;
    reg         mem_reg_write, mem_is_load, mem_is_store, mem_halt, mem_illegal;

    reg         wb_valid;
    reg  [31:0] wb_pc, wb_data;
    reg  [4:0]  wb_rd;
    reg         wb_reg_write, wb_halt, wb_illegal;

    wire [1:0] fwd_a, fwd_b;
    forwarding_unit u_fwd (
        .ex_rs1(ex_rs1), .ex_rs2(ex_rs2),
        .mem_rd(mem_rd), .mem_we(mem_valid & mem_reg_write),
        .wb_rd(wb_rd),   .wb_we(wb_valid & wb_reg_write),
        .fwd_a(fwd_a), .fwd_b(fwd_b)
    );

    wire [31:0] ex_rs1_fwd = (fwd_a == 2'b01) ? mem_result :
                             (fwd_a == 2'b10) ? wb_data    : ex_rs1_val;
    wire [31:0] ex_rs2_fwd = (fwd_b == 2'b01) ? mem_result :
                             (fwd_b == 2'b10) ? wb_data    : ex_rs2_val;

    wire [31:0] alu_a = ex_a_sel_pc    ? ex_pc  : ex_rs1_fwd;
    wire [31:0] alu_b = ex_alu_src_imm ? ex_imm : ex_rs2_fwd;
    wire [31:0] alu_y;
    alu u_alu (.a(alu_a), .b(alu_b), .op(ex_alu_op), .y(alu_y));

    wire [31:0] ex_pc_plus4 = ex_pc + 32'd4;
    wire [31:0] ex_result   = ex_link ? ex_pc_plus4 : alu_y;

    // ---- branch resolution --------------------------------------------------
    wire eq  = (ex_rs1_fwd == ex_rs2_fwd);
    wire lt  = ($signed(ex_rs1_fwd) < $signed(ex_rs2_fwd));
    wire ltu = (ex_rs1_fwd < ex_rs2_fwd);
    reg  cond;
    always @* begin
        case (ex_funct3)
            3'b000:  cond = eq;       // BEQ
            3'b001:  cond = ~eq;      // BNE
            3'b100:  cond = lt;       // BLT
            3'b101:  cond = ~lt;      // BGE
            3'b110:  cond = ltu;      // BLTU
            3'b111:  cond = ~ltu;     // BGEU
            default: cond = 1'b0;
        endcase
    end

    wire        ex_is_ctrl     = ex_valid & (ex_is_branch | ex_is_jal | ex_is_jalr);
    wire [31:0] pc_plus_imm    = ex_pc + ex_imm;
    assign actual_taken        = (ex_is_branch & cond) | ex_is_jal | ex_is_jalr;
    assign actual_target       = ex_is_jalr ? {alu_y[31:1], 1'b0} : pc_plus_imm;

    // Misprediction: wrong direction, wrong target, or a "taken" prediction on
    // an instruction that is not a control-flow instruction at all.
    wire mispredict = ex_valid & (ex_is_ctrl
                        ? ((actual_taken != ex_pred_taken) ||
                           (actual_taken && (ex_pred_target != actual_target)))
                        : ex_pred_taken);

    assign redirect    = mispredict;
    assign redirect_pc = actual_taken ? actual_target : ex_pc_plus4;

    assign bp_upd_en      = ex_is_ctrl;
    assign ex_pc_w        = ex_pc;
    assign ex_is_branch_w = ex_is_branch;

    // =========================================================================
    // EX/MEM pipeline register
    // =========================================================================
    always @(posedge clk) begin
        if (rst) begin
            mem_valid <= 1'b0;     mem_pc <= 32'b0;      mem_result <= 32'b0;
            mem_rs2 <= 32'b0;      mem_rd <= 5'b0;       mem_funct3 <= 3'b0;
            mem_reg_write <= 1'b0; mem_is_load <= 1'b0;  mem_is_store <= 1'b0;
            mem_halt <= 1'b0;      mem_illegal <= 1'b0;
        end else begin
            mem_valid     <= ex_valid;
            mem_pc        <= ex_pc;
            mem_result    <= ex_result;
            mem_rs2       <= ex_rs2_fwd;
            mem_rd        <= ex_rd;
            mem_funct3    <= ex_funct3;
            mem_reg_write <= ex_reg_write;
            mem_is_load   <= ex_is_load;
            mem_is_store  <= ex_is_store;
            mem_halt      <= ex_halt;
            mem_illegal   <= ex_illegal;
        end
    end

    // =========================================================================
    // MEM stage
    // =========================================================================
    assign dmem_addr = mem_result;
    assign dmem_re   = mem_valid & mem_is_load;

    // store: replicate data across byte lanes + byte strobes
    reg [3:0]  wstrb_r;
    reg [31:0] wdata_r;
    always @* begin
        wstrb_r = 4'b0000;
        wdata_r = mem_rs2;
        if (mem_valid && mem_is_store) begin
            case (mem_funct3[1:0])
                2'b00:   begin wstrb_r = 4'b0001 << mem_result[1:0];
                               wdata_r = {4{mem_rs2[7:0]}};  end          // SB
                2'b01:   begin wstrb_r = 4'b0011 << {mem_result[1], 1'b0};
                               wdata_r = {2{mem_rs2[15:0]}}; end          // SH
                default: begin wstrb_r = 4'b1111;
                               wdata_r = mem_rs2;            end          // SW
            endcase
        end
    end
    assign dmem_wstrb = wstrb_r;
    assign dmem_wdata = wdata_r;

    // load: byte-lane select + sign/zero extension
    wire [31:0] ld_shift = dmem_rdata >> {mem_result[1:0], 3'b000};
    reg  [31:0] load_data;
    always @* begin
        case (mem_funct3)
            3'b000:  load_data = {{24{ld_shift[7]}},  ld_shift[7:0]};     // LB
            3'b001:  load_data = {{16{ld_shift[15]}}, ld_shift[15:0]};    // LH
            3'b100:  load_data = {24'b0, ld_shift[7:0]};                  // LBU
            3'b101:  load_data = {16'b0, ld_shift[15:0]};                 // LHU
            default: load_data = ld_shift;                                // LW
        endcase
    end

    // =========================================================================
    // MEM/WB pipeline register
    // =========================================================================
    always @(posedge clk) begin
        if (rst) begin
            wb_valid <= 1'b0;  wb_pc <= 32'b0;  wb_data <= 32'b0;  wb_rd <= 5'b0;
            wb_reg_write <= 1'b0;  wb_halt <= 1'b0;  wb_illegal <= 1'b0;
        end else begin
            wb_valid     <= mem_valid;
            wb_pc        <= mem_pc;
            wb_data      <= mem_is_load ? load_data : mem_result;
            wb_rd        <= mem_rd;
            wb_reg_write <= mem_reg_write;
            wb_halt      <= mem_halt;
            wb_illegal   <= mem_illegal;
        end
    end

    // =========================================================================
    // WB stage
    // =========================================================================
    assign wb_we     = wb_valid & wb_reg_write;
    assign wb_rd_w   = wb_rd;
    assign wb_data_w = wb_data;

    assign halted        = wb_valid & wb_halt;
    assign illegal_instr = wb_valid & wb_illegal;

    // =========================================================================
    // Performance counters
    // =========================================================================
    reg halt_done;
    always @(posedge clk) begin
        if (rst) begin
            halt_done <= 1'b0;
            cnt_cycles <= 0; cnt_instret <= 0; cnt_stalls <= 0; cnt_flushes <= 0;
            cnt_cond_br <= 0; cnt_cond_miss <= 0; cnt_jumps <= 0; cnt_jump_miss <= 0;
        end else if (!halt_done) begin
            cnt_cycles <= cnt_cycles + 1;
            if (wb_valid)                          cnt_instret   <= cnt_instret + 1;
            if (stall)                             cnt_stalls    <= cnt_stalls + 1;
            if (redirect)                          cnt_flushes   <= cnt_flushes + 1;
            if (ex_valid & ex_is_branch)           cnt_cond_br   <= cnt_cond_br + 1;
            if (mispredict & ex_is_branch)         cnt_cond_miss <= cnt_cond_miss + 1;
            if (ex_valid & (ex_is_jal | ex_is_jalr)) cnt_jumps    <= cnt_jumps + 1;
            if (mispredict & (ex_is_jal | ex_is_jalr)) cnt_jump_miss <= cnt_jump_miss + 1;
            if (halted)                            halt_done     <= 1'b1;
        end
    end

    // =========================================================================
    // Debug taps
    // =========================================================================
    assign dbg_pc_if  = pc;
    assign dbg_pc_id  = if_id_pc;
    assign dbg_pc_ex  = ex_pc;
    assign dbg_pc_mem = mem_pc;
    assign dbg_pc_wb  = wb_pc;
    assign dbg_valid  = {wb_valid, mem_valid, ex_valid, if_id_valid, 1'b1};
    assign dbg_stall  = stall;
    assign dbg_flush  = redirect;
    assign dbg_fwd_a  = fwd_a;
    assign dbg_fwd_b  = fwd_b;
endmodule
