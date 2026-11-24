`timescale 1ns/1ps
// One result/cycle; 12 registered stages including SRAM-return capture.
// Bias addition wraps to int32; product rounding wraps to int64 as before.
module kwt_requant_pipe(
    input wire clk,rst_n,valid_in,wide_in,
    input wire signed [31:0] acc,bias,multiplier,
    output reg valid_out,
    output reg signed [15:0] quant,
    output reg [7:0] gelu
);
    reg signed [31:0] a0,b0,m0,sum1,m1;
    reg [7:0] wide;
    reg [1:0] valid;
    wire mv;
    wire signed [63:0] product;
    kwt_mul_pipe u_mul(.clk(clk),.rst_n(rst_n),.valid_in(valid[1]),
        .a(sum1),.b(m1),.valid_out(mv),.product(product));
    reg signed [63:0] rounded;
    wire signed [63:0] scaled=rounded>>>31;
    reg signed [15:0] saturated,quant_index;
    reg wide_round;
    reg [7:0] idx;
    wire signed [8:0] index_sum=$signed(saturated[7:0])+9'sd127;
    wire [7:0] lut;
    kwt_gelu_lut u_lut(.idx(idx),.val(lut));
    reg rv,sv,iv;
    always @(posedge clk) begin
        a0<=acc; b0<=bias; m0<=multiplier;
        sum1<=a0+b0; m1<=m0;
        wide<={wide[6:0],wide_in};
        rounded<=product+64'sd1073741824; wide_round<=wide[7];
        if(wide_round)
            saturated<=(scaled>32767)?16'sd32767:(scaled< -32767)?-16'sd32767:scaled[15:0];
        else
            saturated<=(scaled>127)?16'sd127:(scaled< -127)?-16'sd127:scaled[15:0];
        idx<=(index_sum<0)?0:(index_sum>254)?254:index_sum[7:0];
        quant_index<=saturated;
        quant<=quant_index; gelu<=lut;
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin valid<=0;rv<=0;sv<=0;iv<=0;valid_out<=0;end
        else begin valid<={valid[0],valid_in};rv<=mv;sv<=rv;iv<=sv;valid_out<=iv;end
    end
endmodule
