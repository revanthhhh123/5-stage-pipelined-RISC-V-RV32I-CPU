// -----------------------------------------------------------------------------
// branch_predictor.v : dynamic predictor used in the IF stage
//
//   * Direct-mapped Branch Target Buffer (BTB): remembers the target of every
//     taken control-flow instruction, tagged with the upper PC bits.
//   * Bimodal Branch History Table (BHT): one 2-bit saturating counter per
//     entry (00/01 = not taken, 10/11 = taken).
//   * Prediction is made purely from the PC (before decode): a BTB hit with a
//     counter >= 2 redirects fetch to the stored target in the SAME cycle, so a
//     correctly predicted taken branch costs zero bubbles.
//   * Updated from the EX stage when the real outcome is known.
//   * ENABLE=0 turns the module into "always predict not-taken" so that the
//     benefit of the predictor can be measured (see results in README).
// -----------------------------------------------------------------------------
module branch_predictor #(
    parameter ENABLE     = 1,
    parameter INDEX_BITS = 5
)(
    input         clk,
    input         rst,
    // lookup (IF stage)
    input  [31:0] pc,
    output        pred_taken,
    output [31:0] pred_target,
    // update (EX stage)
    input         upd_en,        // a control-flow instruction is in EX
    input  [31:0] upd_pc,
    input         upd_is_cond,   // conditional branch (vs JAL/JALR)
    input         upd_taken,
    input  [31:0] upd_target
);
    localparam ENTRIES = 1 << INDEX_BITS;
    localparam TAG_W   = 30 - INDEX_BITS;

    reg [ENTRIES-1:0]  btb_valid;
    reg [TAG_W-1:0]    btb_tag    [0:ENTRIES-1];
    reg [29:0]         btb_target [0:ENTRIES-1];
    reg [1:0]          bht        [0:ENTRIES-1];

`ifndef SYNTHESIS
    integer k;
    initial for (k = 0; k < ENTRIES; k = k + 1) begin
        btb_tag[k] = 0; btb_target[k] = 0; bht[k] = 2'b01;
    end
`endif

    // ---------------- lookup ----------------
    wire [INDEX_BITS-1:0] idx = pc[INDEX_BITS+1:2];
    wire [TAG_W-1:0]      tag = pc[31:INDEX_BITS+2];
    wire hit = btb_valid[idx] && (btb_tag[idx] == tag);

    assign pred_taken  = (ENABLE != 0) && hit && bht[idx][1];
    assign pred_target = hit ? {btb_target[idx], 2'b00} : 32'b0;

    // ---------------- update ----------------
    wire [INDEX_BITS-1:0] uidx = upd_pc[INDEX_BITS+1:2];
    wire [TAG_W-1:0]      utag = upd_pc[31:INDEX_BITS+2];
    wire                  uhit = btb_valid[uidx] && (btb_tag[uidx] == utag);
    wire [1:0]            ucnt = bht[uidx];

    always @(posedge clk) begin
        if (rst) begin
            btb_valid <= {ENTRIES{1'b0}};
        end else if (upd_en && (ENABLE != 0)) begin
            if (uhit) begin
                if (!upd_is_cond)       bht[uidx] <= 2'b11;
                else if (upd_taken)     bht[uidx] <= (ucnt == 2'b11) ? 2'b11 : ucnt + 2'b01;
                else                    bht[uidx] <= (ucnt == 2'b00) ? 2'b00 : ucnt - 2'b01;
                if (upd_taken) btb_target[uidx] <= upd_target[31:2];
            end else if (upd_taken) begin                 // allocate on first taken
                btb_valid[uidx]  <= 1'b1;
                btb_tag[uidx]    <= utag;
                btb_target[uidx] <= upd_target[31:2];
                bht[uidx]        <= upd_is_cond ? 2'b10 : 2'b11;
            end
        end
    end
endmodule
