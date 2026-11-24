`timescale 1ns / 1ps
// int32 accumulator -> int8 requantization.
// Fixed Q1.31 multiplier, round-half-up, symmetric saturation to [-127, 127].
//
//   q_out = sat8( (acc * m_int + 2^30) >>> 31 )
//
// Bit-exact reference: tools/fixed_sim.py (requant_i32_to_i8)
module kwt_requant (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               valid_in,
    input  wire signed [31:0] acc_in,
    input  wire signed [31:0] m_int,     // round(M * 2^31), M = Sx*Sw/Sy
    output reg  signed [7:0]  q_out,
    output reg                valid_out
);

    wire signed [63:0] prod    = acc_in * m_int;
    wire signed [63:0] rounded = prod + 64'sd1073741824;   // 1 << 30
    wire signed [63:0] shifted = rounded >>> 31;

    wire signed [7:0] saturated =
        (shifted > 64'sd127)  ? 8'sd127  :
        (shifted < -64'sd127) ? -8'sd127 : shifted[7:0];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            q_out     <= 8'sd0;
            valid_out <= 1'b0;
        end else begin
            valid_out <= valid_in;
            if (valid_in)
                q_out <= saturated;
        end
    end

endmodule
