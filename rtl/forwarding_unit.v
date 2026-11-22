// -----------------------------------------------------------------------------
// forwarding_unit.v : operand bypass select for the EX stage
//   2'b00 : use value read in ID (register file)
//   2'b01 : forward from EX/MEM  (ALU result of the previous instruction)
//   2'b10 : forward from MEM/WB  (ALU or load result, two instructions back)
// EX/MEM has priority because it holds the most recent value.
// (A load directly followed by its consumer is handled by the hazard unit.)
// -----------------------------------------------------------------------------
module forwarding_unit (
    input  [4:0] ex_rs1,
    input  [4:0] ex_rs2,
    input  [4:0] mem_rd,
    input        mem_we,
    input  [4:0] wb_rd,
    input        wb_we,
    output [1:0] fwd_a,
    output [1:0] fwd_b
);
    assign fwd_a = (mem_we && mem_rd != 5'd0 && mem_rd == ex_rs1) ? 2'b01 :
                   (wb_we  && wb_rd  != 5'd0 && wb_rd  == ex_rs1) ? 2'b10 : 2'b00;
    assign fwd_b = (mem_we && mem_rd != 5'd0 && mem_rd == ex_rs2) ? 2'b01 :
                   (wb_we  && wb_rd  != 5'd0 && wb_rd  == ex_rs2) ? 2'b10 : 2'b00;
endmodule
