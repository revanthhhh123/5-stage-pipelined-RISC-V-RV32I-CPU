// -----------------------------------------------------------------------------
// tb_alu.v : unit test - ALU vs. an independent behavioural reference
//   directed corner cases + 200k constrained-random vectors per operation
// -----------------------------------------------------------------------------
`timescale 1ns/1ps
`include "riscv_defs.vh"

module tb_alu;
    reg  [31:0] a, b;
    reg  [3:0]  op;
    wire [31:0] y;
    alu dut (.a(a), .b(b), .op(op), .y(y));

    integer errors = 0, checks = 0, n, k;
    reg [31:0] exp;
    reg signed [31:0] sa, sb;
    integer sh;

    function [31:0] ref_model(input [3:0] o, input [31:0] x, input [31:0] z);
        reg signed [31:0] sx, sz;
        integer s, j;
        reg [31:0] t;
        begin
            sx = x; sz = z; s = z[4:0];
            case (o)
                `ALU_ADD:   ref_model = x + z;
                `ALU_SUB:   ref_model = x + (~z) + 1;
                `ALU_SLL:   begin t = x; for (j = 0; j < s; j = j + 1) t = {t[30:0], 1'b0}; ref_model = t; end
                `ALU_SRL:   begin t = x; for (j = 0; j < s; j = j + 1) t = {1'b0, t[31:1]}; ref_model = t; end
                `ALU_SRA:   begin t = x; for (j = 0; j < s; j = j + 1) t = {t[31], t[31:1]}; ref_model = t; end
                `ALU_SLT:   ref_model = (sx < sz) ? 32'd1 : 32'd0;
                `ALU_SLTU:  ref_model = (x < z)   ? 32'd1 : 32'd0;
                `ALU_XOR:   ref_model = (x | z) & ~(x & z);
                `ALU_OR:    ref_model = x | z;
                `ALU_AND:   ref_model = x & z;
                `ALU_PASSB: ref_model = z;
                default:    ref_model = 32'd0;
            endcase
        end
    endfunction

    task check;
        begin
            #1; exp = ref_model(op, a, b); checks = checks + 1;
            if (y !== exp) begin
                errors = errors + 1;
                if (errors < 10) $display("MISMATCH op=%0d a=%h b=%h got=%h exp=%h", op, a, b, y, exp);
            end
        end
    endtask

    reg [31:0] corner [0:7];
    integer ci, cj;
    initial begin
        corner[0] = 32'h0;         corner[1] = 32'h1;          corner[2] = 32'hFFFFFFFF;
        corner[3] = 32'h7FFFFFFF;  corner[4] = 32'h80000000;   corner[5] = 32'h80000001;
        corner[6] = 32'h0000001F;  corner[7] = 32'hAAAA5555;

        for (op = 0; op <= 10; op = op + 1) begin
            for (ci = 0; ci < 8; ci = ci + 1)
                for (cj = 0; cj < 8; cj = cj + 1) begin a = corner[ci]; b = corner[cj]; check; end
            for (n = 0; n < 200000; n = n + 1) begin
                a = $random; b = $random; check;
            end
        end

        $display("tb_alu: %0d checks, %0d errors", checks, errors);
        if (errors == 0) $display("TB_ALU PASS"); else $display("TB_ALU FAIL");
        $finish;
    end
endmodule
