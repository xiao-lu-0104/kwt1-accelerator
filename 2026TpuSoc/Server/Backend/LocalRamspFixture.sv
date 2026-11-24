`timescale 1ns/1ps
// LOCAL TEST DOUBLE ONLY. The server runner never compiles this file.
// Checks adapter polarity/control wiring; contains no vendor timing checks.
module RAMSP1024X16 (
    output logic [15:0] Q,
    input logic CLK, CEN, GWEN,
    input logic [15:0] WEN,
    input logic [9:0] A,
    input logic [15:0] D,
    input logic [2:0] EMA,
    input logic [1:0] EMAW,
    input logic RET1N
);
    logic [15:0] Words [1024];
    always @(posedge CLK) begin
        if (EMA !== 3'd2 || EMAW !== 2'd0 || RET1N !== 1'b1)
            $fatal(1, "Fixture: bad static SRAM control pins");
        if (!CEN) begin
            if (!GWEN) begin
                for (int Bit = 0; Bit < 16; Bit++) if (!WEN[Bit]) Words[A][Bit] <= D[Bit];
            end else Q <= #1.25 Words[A];
        end
    end
endmodule
