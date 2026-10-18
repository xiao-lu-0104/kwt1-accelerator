`timescale 1ns / 1ps
// 4-channel parallel GEMM primitive: one activation vector against 4 weight rows.
// Each cycle produces 4 int32 accumulators, i.e. 4 x 64 = 256 MAC/cycle.
//
// Weight layout: wgt_flat[c*64*4 + i*4 +: 4] = weight of channel c, input i (int4)
// The four channels map to the four output channels processed in parallel.
module kwt_gemm4 #(
    parameter WB = 4
)(
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire                 valid_in,
    input  wire [64*8-1:0]      act_flat,
    input  wire [4*64*WB-1:0]   wgt_flat,
    input  wire signed [31:0]   acc_in0,
    input  wire signed [31:0]   acc_in1,
    input  wire signed [31:0]   acc_in2,
    input  wire signed [31:0]   acc_in3,
    output wire signed [31:0]   acc0,
    output wire signed [31:0]   acc1,
    output wire signed [31:0]   acc2,
    output wire signed [31:0]   acc3,
    output wire                 valid_out
);

    wire v0, v1, v2, v3;

    kwt_dot64 #(.WB(WB)) u_ch0 (
        .clk      (clk),
        .rst_n    (rst_n),
        .valid_in (valid_in),
        .act_flat (act_flat),
        .wgt_flat (wgt_flat[0*64*WB +: 64*WB]),
        .acc_in   (acc_in0),
        .acc_out  (acc0),
        .valid_out(v0)
    );

    kwt_dot64 #(.WB(WB)) u_ch1 (
        .clk      (clk),
        .rst_n    (rst_n),
        .valid_in (valid_in),
        .act_flat (act_flat),
        .wgt_flat (wgt_flat[1*64*WB +: 64*WB]),
        .acc_in   (acc_in1),
        .acc_out  (acc1),
        .valid_out(v1)
    );

    kwt_dot64 #(.WB(WB)) u_ch2 (
        .clk      (clk),
        .rst_n    (rst_n),
        .valid_in (valid_in),
        .act_flat (act_flat),
        .wgt_flat (wgt_flat[2*64*WB +: 64*WB]),
        .acc_in   (acc_in2),
        .acc_out  (acc2),
        .valid_out(v2)
    );

    kwt_dot64 #(.WB(WB)) u_ch3 (
        .clk      (clk),
        .rst_n    (rst_n),
        .valid_in (valid_in),
        .act_flat (act_flat),
        .wgt_flat (wgt_flat[3*64*WB +: 64*WB]),
        .acc_in   (acc_in3),
        .acc_out  (acc3),
        .valid_out(v3)
    );

    assign valid_out = v0 & v1 & v2 & v3;

endmodule
