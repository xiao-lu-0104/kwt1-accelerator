`timescale 1ns / 1ps
// Exact low 64 bits of a signed product, six registered stages, II=1.
// 16-bit limbs keep each partial product within one FPGA DSP multiplier;
// registered diagonal reduction and carry propagation avoid DSP cascades.
// Arithmetic is modulo 2^64, matching Verilog's 64-bit product truncation.
module kwt_mul_pipe #(parameter A_BITS=32, parameter B_BITS=32)(
    input wire clk, input wire rst_n, input wire valid_in,
    input wire signed [A_BITS-1:0] a,
    input wire signed [B_BITS-1:0] b,
    output wire valid_out, output reg signed [63:0] product
);
    localparam NA=(A_BITS+15)/16, NB=(B_BITS+15)/16;
    wire signed [NA*16-1:0] ax=a;
    wire signed [NB*16-1:0] bx=b;
    wire signed [39:0] p[0:15];
    genvar i,j;
    generate for(i=0;i<4;i=i+1) begin: g_a
        for(j=0;j<4;j=j+1) begin: g_b
            if(i<NA&&j<NB&&i+j<4) begin: g_product
                wire signed [16:0] al={(i==NA-1)?ax[NA*16-1]:1'b0,ax[i*16 +: 16]};
                wire signed [16:0] bl={(j==NB-1)?bx[NB*16-1]:1'b0,bx[j*16 +: 16]};
                reg signed [33:0] pp;
                always @(posedge clk) pp<=al*bl;
                assign p[i*4+j]={{6{pp[33]}},pp};
            end else assign p[i*4+j]=40'sd0;
        end
    end endgenerate
    reg [5:0] valid;
    always @(posedge clk or negedge rst_n)
        if(!rst_n) valid<=0; else valid<={valid[4:0],valid_in};
    assign valid_out=valid[5];

    reg signed [39:0] d0_2,d1_2,d2a_2,d2b_2,d3a_2,d3b_2;
    reg signed [39:0] d0_3,d1_3,d2_3,d3_3;
    reg signed [39:0] carry1_4,d2_4,d3_4,carry2_5,d3_5;
    reg [15:0] lo0_4,lo0_5,lo1_5;
    wire signed [39:0] high= d3_5+(carry2_5>>>16);
    always @(posedge clk) begin
        d0_2<=p[0]; d1_2<=p[1]+p[4];
        d2a_2<=p[2]+p[5]; d2b_2<=p[8];
        d3a_2<=p[3]+p[6]; d3b_2<=p[9]+p[12];
        d0_3<=d0_2; d1_3<=d1_2;
        d2_3<=d2a_2+d2b_2; d3_3<=d3a_2+d3b_2;
        carry1_4<=d1_3+(d0_3>>>16);
        lo0_4<=d0_3[15:0]; d2_4<=d2_3; d3_4<=d3_3;
        carry2_5<=d2_4+(carry1_4>>>16);
        lo0_5<=lo0_4; lo1_5<=carry1_4[15:0]; d3_5<=d3_4;
        product<={high[15:0],carry2_5[15:0],lo1_5,lo0_5};
    end
    // synthesis translate_off
    initial if(A_BITS<1||A_BITS>64||B_BITS<1||B_BITS>64)
        $fatal(1,"unsupported multiplier width");
    // synthesis translate_on
endmodule
