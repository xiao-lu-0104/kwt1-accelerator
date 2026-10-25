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

    // Exact product widths, then one extra bit per balanced reduction level.
    // Six adder levels replace the procedural chain of 64 full-width adds.
    localparam PW = 8 + WB;
    wire signed [PW-1:0] product [0:63];
    wire signed [PW:0] l1 [0:31];
    wire signed [PW+1:0] l2 [0:15];
    wire signed [PW+2:0] l3 [0:7];
    wire signed [PW+3:0] l4 [0:3];
    wire signed [PW+4:0] l5 [0:1];
    wire signed [PW+5:0] total;
    genvar gi;
    generate
        for (gi=0; gi<64; gi=gi+1) begin : g_product
            assign product[gi] = $signed(act_flat[gi*8 +: 8]) *
                                 $signed(wgt_flat[gi*WB +: WB]);
        end
        for (gi=0; gi<32; gi=gi+1) begin : g_l1
            assign l1[gi] = $signed({product[2*gi][PW-1], product[2*gi]}) +
                            $signed({product[2*gi+1][PW-1], product[2*gi+1]});
        end
        for (gi=0; gi<16; gi=gi+1) begin : g_l2
            assign l2[gi] = $signed({l1[2*gi][PW], l1[2*gi]}) +
                            $signed({l1[2*gi+1][PW], l1[2*gi+1]});
        end
        for (gi=0; gi<8; gi=gi+1) begin : g_l3
            assign l3[gi] = $signed({l2[2*gi][PW+1], l2[2*gi]}) +
                            $signed({l2[2*gi+1][PW+1], l2[2*gi+1]});
        end
        for (gi=0; gi<4; gi=gi+1) begin : g_l4
            assign l4[gi] = $signed({l3[2*gi][PW+2], l3[2*gi]}) +
                            $signed({l3[2*gi+1][PW+2], l3[2*gi+1]});
        end
        for (gi=0; gi<2; gi=gi+1) begin : g_l5
            assign l5[gi] = $signed({l4[2*gi][PW+3], l4[2*gi]}) +
                            $signed({l4[2*gi+1][PW+3], l4[2*gi+1]});
        end
    endgenerate
    assign total = $signed({l5[0][PW+4], l5[0]}) +
                   $signed({l5[1][PW+4], l5[1]});
    // Preserve the original modulo-2^32 accumulator semantics.
    wire signed [31:0] sum_comb = acc_in + total;

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
