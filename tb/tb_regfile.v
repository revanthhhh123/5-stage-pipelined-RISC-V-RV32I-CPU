// -----------------------------------------------------------------------------
// tb_regfile.v : unit test - x0, write/read, write-through bypass
// -----------------------------------------------------------------------------
`timescale 1ns/1ps
module tb_regfile;
    reg clk = 0, we = 0;
    reg [4:0] waddr = 0, ra1 = 0, ra2 = 0;
    reg [31:0] wdata = 0;
    wire [31:0] rd1, rd2;
    regfile dut (.clk(clk), .we(we), .waddr(waddr), .wdata(wdata),
                 .raddr1(ra1), .raddr2(ra2), .rdata1(rd1), .rdata2(rd2));
    always #5 clk = ~clk;

    integer errors = 0, i;
    reg [31:0] model [0:31];

    task expect32(input [31:0] got, input [31:0] exp, input [255:0] what);
        begin
            if (got !== exp) begin
                errors = errors + 1;
                $display("FAIL %0s: got %h exp %h", what, got, exp);
            end
        end
    endtask

    initial begin
        for (i = 0; i < 32; i = i + 1) model[i] = 0;
        // 1. write every register with a unique value
        for (i = 0; i < 32; i = i + 1) begin
            @(negedge clk); we = 1; waddr = i; wdata = 32'hA5A50000 + i * 32'h101;
            if (i != 0) model[i] = wdata;
        end
        @(negedge clk); we = 0;
        // 2. read back (x0 must stay zero)
        for (i = 0; i < 32; i = i + 1) begin
            ra1 = i; ra2 = 31 - i; #1;
            expect32(rd1, model[i],      "port1 readback");
            expect32(rd2, model[31 - i], "port2 readback");
        end
        // 3. write-through bypass: read in same cycle as write
        @(negedge clk); we = 1; waddr = 5'd9; wdata = 32'hDEADBEEF; ra1 = 5'd9; ra2 = 5'd9; #1;
        expect32(rd1, 32'hDEADBEEF, "bypass port1");
        expect32(rd2, 32'hDEADBEEF, "bypass port2");
        // 4. bypass must NOT apply to x0
        @(negedge clk); we = 1; waddr = 5'd0; wdata = 32'hFFFFFFFF; ra1 = 5'd0; #1;
        expect32(rd1, 32'h0, "x0 bypass");
        // 5. write enable low must not write
        @(negedge clk); we = 0; waddr = 5'd9; wdata = 32'h1234; @(negedge clk); ra1 = 5'd9; #1;
        expect32(rd1, 32'hDEADBEEF, "we=0 no write");

        if (errors == 0) $display("TB_REGFILE PASS"); else $display("TB_REGFILE FAIL (%0d)", errors);
        $finish;
    end
endmodule
