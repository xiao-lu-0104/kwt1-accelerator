`timescale 1ns / 1ps
// Residual alignment adder: two int8 tensors with independent scales are
// brought into a common Q10 domain and summed into int16.
//
//   y = sat16((a*ma + b*mb + 512) >>> 10)
//
// Bit-exact with fixed_encoder.align_add.
module kwt_align_add (
    input  wire signed [7:0]  a,
    input  wire signed [7:0]  b,
    input  wire signed [15:0] ma,
    input  wire signed [15:0] mb,
    output wire signed [15:0] y
);
    localparam signed [15:0] LIM = 16'sd32767;

    wire signed [31:0] p1  = a * ma;
    wire signed [31:0] p2  = b * mb;
    wire signed [31:0] sum = p1 + p2 + 32'sd512;
    wire signed [31:0] shr = sum >>> 10;

    assign y = (shr > 32'sd32767)  ? LIM :
               (shr < -32'sd32768) ? -16'sd32768 : shr[15:0];
endmodule
