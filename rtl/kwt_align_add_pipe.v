`timescale 1ns/1ps
// Four stages: indexed input capture, products, rounded sum, saturation.
module kwt_align_add_pipe(
    input wire clk,rst_n,valid_in,
    input wire signed [7:0] a,b,
    input wire signed [15:0] ma,mb,
    output wire valid_out,
    output reg signed [15:0] y
);
    reg signed [7:0] ar,br;
    reg signed [15:0] mar,mbr;
    reg signed [23:0] p1,p2;
    reg signed [31:0] rounded;
    wire signed [31:0] shifted=rounded>>>10;
    reg [3:0] valid;
    always @(posedge clk) begin
        ar<=a;br<=b;mar<=ma;mbr<=mb;
        p1<=ar*mar;p2<=br*mbr;
        rounded<=$signed(p1)+$signed(p2)+32'sd512;
        y<=(shifted>32767)?16'sd32767:(shifted< -32768)?-16'sd32768:shifted[15:0];
    end
    always @(posedge clk or negedge rst_n)
        if(!rst_n) valid<=0;else valid<={valid[2:0],valid_in};
    assign valid_out=valid[3];
endmodule
