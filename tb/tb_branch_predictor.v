// -----------------------------------------------------------------------------
// tb_branch_predictor.v : unit test - learning behaviour of BTB + 2-bit BHT
// -----------------------------------------------------------------------------
`timescale 1ns/1ps
module tb_branch_predictor;
    reg clk = 0, rst = 1;
    reg [31:0] pc = 0, upd_pc = 0, upd_target = 0;
    reg upd_en = 0, upd_is_cond = 1, upd_taken = 0;
    wire pt; wire [31:0] ptgt;
    wire pt_off; wire [31:0] ptgt_off;

    branch_predictor #(.ENABLE(1), .INDEX_BITS(4)) dut (
        .clk(clk), .rst(rst), .pc(pc), .pred_taken(pt), .pred_target(ptgt),
        .upd_en(upd_en), .upd_pc(upd_pc), .upd_is_cond(upd_is_cond),
        .upd_taken(upd_taken), .upd_target(upd_target));

    branch_predictor #(.ENABLE(0), .INDEX_BITS(4)) dut_off (
        .clk(clk), .rst(rst), .pc(pc), .pred_taken(pt_off), .pred_target(ptgt_off),
        .upd_en(upd_en), .upd_pc(upd_pc), .upd_is_cond(upd_is_cond),
        .upd_taken(upd_taken), .upd_target(upd_target));

    always #5 clk = ~clk;
    integer errors = 0;

    task update(input [31:0] p, input cond, input taken, input [31:0] tgt);
        begin
            @(negedge clk); upd_en = 1; upd_pc = p; upd_is_cond = cond; upd_taken = taken; upd_target = tgt;
            @(negedge clk); upd_en = 0;
        end
    endtask

    task expect_pred(input [31:0] p, input exp_taken, input [31:0] exp_tgt, input [255:0] what);
        begin
            pc = p; #1;
            if (pt !== exp_taken || (exp_taken && ptgt !== exp_tgt)) begin
                errors = errors + 1;
                $display("FAIL %0s: pred=%b tgt=%h (exp %b %h)", what, pt, ptgt, exp_taken, exp_tgt);
            end
        end
    endtask

    initial begin
        repeat (2) @(negedge clk); rst = 0;
        expect_pred(32'h100, 0, 0, "cold: not taken");
        update(32'h100, 1, 1, 32'h80);                 // first taken -> allocate, weakly taken
        expect_pred(32'h100, 1, 32'h80, "after 1 taken");
        update(32'h100, 1, 1, 32'h80);                 // strongly taken
        update(32'h100, 1, 0, 32'h80);                 // one not-taken: still taken (hysteresis)
        expect_pred(32'h100, 1, 32'h80, "hysteresis");
        update(32'h100, 1, 0, 32'h80);
        update(32'h100, 1, 0, 32'h80);                 // now weakly/strongly not taken
        expect_pred(32'h100, 0, 0, "learned not-taken");
        // unconditional jump: always predicted taken after first execution
        update(32'h204, 0, 1, 32'h400);
        expect_pred(32'h204, 1, 32'h400, "jal learned");
        // aliasing: same index, different tag must not hit
        expect_pred(32'h204 + (32'h4 << 4) * 4, 0, 0, "alias miss");   // different upper bits
        // disabled predictor never predicts taken
        pc = 32'h204; #1;
        if (pt_off !== 1'b0) begin errors = errors + 1; $display("FAIL disabled predictor predicts taken"); end

        if (errors == 0) $display("TB_BP PASS"); else $display("TB_BP FAIL (%0d)", errors);
        $finish;
    end
endmodule
