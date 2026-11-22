// -----------------------------------------------------------------------------
// hazard_unit.v : load-use hazard detection
//   A load produces its data at the end of MEM, so a consumer that is directly
//   behind it (in ID while the load is in EX) must wait ONE cycle. We freeze
//   PC and IF/ID and inject a bubble into ID/EX; afterwards the value is
//   forwarded from MEM/WB.
// -----------------------------------------------------------------------------
module hazard_unit (
    input        id_valid,
    input        id_uses_rs1,
    input        id_uses_rs2,
    input  [4:0] id_rs1,
    input  [4:0] id_rs2,
    input        ex_is_load,
    input  [4:0] ex_rd,
    output       load_use_stall
);
    assign load_use_stall = id_valid && ex_is_load && (ex_rd != 5'd0) &&
                            ((id_uses_rs1 && ex_rd == id_rs1) ||
                             (id_uses_rs2 && ex_rd == id_rs2));
endmodule
