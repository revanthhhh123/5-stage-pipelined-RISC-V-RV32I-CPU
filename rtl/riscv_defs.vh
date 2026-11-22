// -----------------------------------------------------------------------------
// riscv_defs.vh : opcode and ALU-operation encodings shared by all RTL modules
// -----------------------------------------------------------------------------
`ifndef RISCV_DEFS_VH
`define RISCV_DEFS_VH

// RV32I major opcodes
`define OPC_LUI     7'b0110111
`define OPC_AUIPC   7'b0010111
`define OPC_JAL     7'b1101111
`define OPC_JALR    7'b1100111
`define OPC_BRANCH  7'b1100011
`define OPC_LOAD    7'b0000011
`define OPC_STORE   7'b0100011
`define OPC_IMM     7'b0010011
`define OPC_REG     7'b0110011
`define OPC_FENCE   7'b0001111
`define OPC_SYSTEM  7'b1110011

// Internal ALU operation codes
`define ALU_ADD     4'd0
`define ALU_SUB     4'd1
`define ALU_SLL     4'd2
`define ALU_SLT     4'd3
`define ALU_SLTU    4'd4
`define ALU_XOR     4'd5
`define ALU_SRL     4'd6
`define ALU_SRA     4'd7
`define ALU_OR      4'd8
`define ALU_AND     4'd9
`define ALU_PASSB   4'd10

`endif
