`timescale 1ns / 1ps
// 64-point dot product: int8 activation x int4 weight -> int32 accumulator.
// Purely combinational MAC tree followed by one output register.
// Bit-exact reference: tools/fixed_sim.py
module kwt_dot64 #(
    parameter WB = 4                      // weight width: 4 or 8
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               valid_in,
    input  wire [64*8-1:0]    act_flat,   // act_flat[i*8 +: 8] = activation i (int8)
    input  wire [64*WB-1:0]   wgt_flat,   // weight i (int4 or int8, two's complement)
    input  wire signed [31:0] acc_in,     // running accumulator for multi-segment GEMM
    output reg  signed [31:0] acc_out,
    output reg                valid_out
);

    wire signed [7:0] w_arr [0:63];
    genvar gi;
    generate
        for (gi = 0; gi < 64; gi = gi + 1) begin : g_sx
            if (WB == 8)
                assign w_arr[gi] = $signed(wgt_flat[gi*8 +: 8]);
            else
                assign w_arr[gi] = $signed({{4{wgt_flat[gi*4+3]}}, wgt_flat[gi*4 +: 4]});
        end
    endgenerate

    integer i;
    reg signed [7:0]  a;
    reg signed [31:0] sum_comb;

    always @(*) begin
        sum_comb = acc_in;
        for (i = 0; i < 64; i = i + 1) begin
            a = $signed(act_flat[i*8 +: 8]);
            sum_comb = sum_comb + $signed(a) * $signed(w_arr[i]);
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc_out   <= 32'sd0;
            valid_out <= 1'b0;
        end else begin
            valid_out <= valid_in;
            if (valid_in)
                acc_out <= sum_comb;
        end
    end

endmodule
