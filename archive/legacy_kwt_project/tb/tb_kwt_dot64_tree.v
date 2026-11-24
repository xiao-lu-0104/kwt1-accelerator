`timescale 1ns/1ps
module dot_tree_check #(parameter WB=4)(output reg finished);
reg clk=0; always #5 clk=~clk;
reg rst_n=0, valid=0;
reg [511:0] a=0;
reg [64*WB-1:0] w=0;
reg signed [31:0] acc=0, expected;
wire signed [31:0] result;
wire v;
integer i,n;
reg signed [7:0] av;
reg signed [WB-1:0] wv;
kwt_dot64 #(.WB(WB)) dut(clk,rst_n,valid,a,w,acc,result,v);
initial begin
  finished=0;
  repeat(2) @(negedge clk);
  rst_n=1;
  for(n=0;n<1000;n=n+1) begin
    @(negedge clk);
    valid=(n<2 || n%7!=0); acc=$random; expected=acc;
    for(i=0;i<64;i=i+1) begin
      av=(n==0)?-128:(n==1)?127:$random;
      wv=(n==0)?-(1<<(WB-1)):(n==1)?((1<<(WB-1))-1):$random;
      a[i*8+:8]=av; w[i*WB+:WB]=wv;
      expected=expected+av*wv;
    end
    @(posedge clk); #1;
    if(v !== valid || (valid && result !== expected))
      $fatal(1,"FAIL: WB=%0d vector=%0d",WB,n);
  end
  @(negedge clk); rst_n=0; #1;
  if(v !== 0 || result !== 0) $fatal(1,"FAIL: reset");
  finished=1;
end
endmodule
module tb_kwt_dot64_tree;
wire a,b;
dot_tree_check #(.WB(4)) u4(a);
dot_tree_check #(.WB(8)) u8(b);
initial begin
 wait(a && b);
 $display("PASS: balanced dot64, W4/W8, 2000 cases including overflow and valid gaps");
 $finish;
end
endmodule
