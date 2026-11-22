// -----------------------------------------------------------------------------
// memories.v : behavioural memory models (SIMULATION ONLY)
//   Both memories are initialised from the same program image (+PROG=file.hex),
//   so code and .data live in one flat 16 KiB address space but are accessed
//   through separate ports (Harvard). Self-modifying code is not supported.
// -----------------------------------------------------------------------------
module imem #(parameter WORDS = 4096) (
    input  [31:0] addr,
    output [31:0] rdata
);
    localparam AW = $clog2(WORDS);
    reg [31:0] mem [0:WORDS-1];
    integer i;
    reg [1023:0] fname;
    initial begin
        for (i = 0; i < WORDS; i = i + 1) mem[i] = 32'h0000_0013;
        if ($value$plusargs("PROG=%s", fname)) $readmemh(fname, mem);
    end
    assign rdata = mem[addr[AW+1:2]];
endmodule

module dmem #(parameter WORDS = 4096) (
    input         clk,
    input  [31:0] addr,
    input  [31:0] wdata,
    input  [3:0]  wstrb,
    input         re,
    output [31:0] rdata
);
    localparam AW = $clog2(WORDS);
    reg [31:0] mem [0:WORDS-1];
    integer i;
    reg [1023:0] fname;
    initial begin
        for (i = 0; i < WORDS; i = i + 1) mem[i] = 32'h0;
        if ($value$plusargs("PROG=%s", fname)) $readmemh(fname, mem);
    end

    wire [AW-1:0] widx = addr[AW+1:2];
    always @(posedge clk) begin
        if (wstrb[0]) mem[widx][7:0]   <= wdata[7:0];
        if (wstrb[1]) mem[widx][15:8]  <= wdata[15:8];
        if (wstrb[2]) mem[widx][23:16] <= wdata[23:16];
        if (wstrb[3]) mem[widx][31:24] <= wdata[31:24];
    end
    assign rdata = mem[widx];
endmodule
