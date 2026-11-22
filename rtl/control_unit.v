// -----------------------------------------------------------------------------
// control_unit.v : main decoder (ID stage). Pure combinational.
//   uses_rs1/uses_rs2 tell the hazard unit which source registers are really
//   read, so that load-use stalls are not inserted needlessly.
// -----------------------------------------------------------------------------
`include "riscv_defs.vh"

module control_unit (
    input  [6:0] opcode,
    input  [2:0] funct3,
    input        funct7_5,        // instr[30]
    output reg   reg_write,
    output reg   mem_read,
    output reg   mem_write,
    output reg   alu_src_imm,     // ALU operand B = immediate
    output reg   a_sel_pc,        // ALU operand A = PC (AUIPC)
    output reg   is_branch,
    output reg   is_jal,
    output reg   is_jalr,
    output reg   link,            // result = PC+4 (JAL/JALR)
    output reg   halt,            // ECALL / EBREAK / illegal  -> stop simulation
    output reg   illegal,
    output reg   uses_rs1,
    output reg   uses_rs2,
    output reg [3:0] alu_op
);
    function [3:0] f3_to_alu;
        input [2:0] f3;
        input       f7_5;
        input       is_reg;
        begin
            case (f3)
                3'b000: f3_to_alu = (is_reg & f7_5) ? `ALU_SUB : `ALU_ADD;
                3'b001: f3_to_alu = `ALU_SLL;
                3'b010: f3_to_alu = `ALU_SLT;
                3'b011: f3_to_alu = `ALU_SLTU;
                3'b100: f3_to_alu = `ALU_XOR;
                3'b101: f3_to_alu = f7_5 ? `ALU_SRA : `ALU_SRL;
                3'b110: f3_to_alu = `ALU_OR;
                default: f3_to_alu = `ALU_AND;
            endcase
        end
    endfunction

    always @* begin
        reg_write = 0; mem_read = 0; mem_write = 0; alu_src_imm = 0;
        a_sel_pc = 0; is_branch = 0; is_jal = 0; is_jalr = 0; link = 0;
        halt = 0; illegal = 0; uses_rs1 = 0; uses_rs2 = 0;
        alu_op = `ALU_ADD;

        case (opcode)
            `OPC_LUI:    begin reg_write = 1; alu_src_imm = 1; alu_op = `ALU_PASSB; end
            `OPC_AUIPC:  begin reg_write = 1; alu_src_imm = 1; a_sel_pc = 1; end
            `OPC_JAL:    begin reg_write = 1; is_jal = 1; link = 1; end
            `OPC_JALR:   begin reg_write = 1; is_jalr = 1; link = 1; alu_src_imm = 1;
                               uses_rs1 = 1; end
            `OPC_BRANCH: begin is_branch = 1; uses_rs1 = 1; uses_rs2 = 1; end
            `OPC_LOAD:   begin reg_write = 1; mem_read = 1; alu_src_imm = 1; uses_rs1 = 1; end
            `OPC_STORE:  begin mem_write = 1; alu_src_imm = 1; uses_rs1 = 1; uses_rs2 = 1; end
            `OPC_IMM:    begin reg_write = 1; alu_src_imm = 1; uses_rs1 = 1;
                               alu_op = f3_to_alu(funct3, funct7_5, 1'b0); end
            `OPC_REG:    begin reg_write = 1; uses_rs1 = 1; uses_rs2 = 1;
                               alu_op = f3_to_alu(funct3, funct7_5, 1'b1); end
            `OPC_FENCE:  ;                                   // treated as NOP
            `OPC_SYSTEM: halt = 1;                           // ECALL / EBREAK
            default:     begin halt = 1; illegal = 1; end
        endcase
    end
endmodule
