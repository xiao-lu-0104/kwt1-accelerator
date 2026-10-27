`timescale 1ns / 1ps
module mul_pipe_case #(parameter AB=32,parameter BB=32)(output reg finished);
    reg clk=0,rst_n=0,valid_in=0;
    reg signed [AB-1:0] a=0;
    reg signed [BB-1:0] b=0;
    wire valid_out;
    wire signed [63:0] product;
    reg [5:0] expected_valid=0;
    reg [63:0] expected[0:5];
    reg signed [127:0] full_product;
    integer n,k,seed=19083,errors=0;
    kwt_mul_pipe #(.A_BITS(AB),.B_BITS(BB)) dut(.*);
    always #5 clk=~clk;
    always @(posedge clk) begin
        if(!rst_n) expected_valid=0;
        else begin
            for(k=5;k>0;k=k-1) expected[k]=expected[k-1];
            full_product=$signed(a)*$signed(b);
            expected[0]=full_product[63:0];
            expected_valid={expected_valid[4:0],valid_in};
        end
        #1;
        if(valid_out!==expected_valid[5] || (valid_out&&product!==expected[5])) begin
            errors=errors+1;
            if(errors<3) $display("MISMATCH multiplier %0dx%0d got=%h exp=%h",AB,BB,product,expected[5]);
        end
    end
    initial begin
        finished=0;
        repeat(3) @(negedge clk);rst_n=1;
        for(n=0;n<1000;n=n+1) begin
            @(negedge clk); valid_in=(n%9!=0);
            a={$random(seed),$random(seed)}; b={$random(seed),$random(seed)};
            if(n<4) begin
                a=(n%2)?((64'd1<<(AB-1))-1):(64'd1<<(AB-1));
                b=(n<2)?((64'd1<<(BB-1))-1):(64'd1<<(BB-1));
            end
            if(n==400) begin
                rst_n=0;repeat(2) @(negedge clk);rst_n=1;
            end
        end
        @(negedge clk);valid_in=0;
        repeat(8) @(negedge clk);
        if(errors) $fatal(1,"multiplier scalar reference failed %0dx%0d",AB,BB);
        $display("PASS: multiplier %0dx%0d random/boundary/gaps/reset",AB,BB);
        finished=1;
    end
endmodule
module tb_kwt_mul_pipe;
    wire a,b,c,d;
    mul_pipe_case #(.AB(17),.BB(32)) t0(a);
    mul_pipe_case #(.AB(41),.BB(16)) t1(b);
    mul_pipe_case #(.AB(32),.BB(64)) t2(c);
    mul_pipe_case #(.AB(64),.BB(64)) t3(d);
    initial begin wait(a&&b&&c&&d);$display("PASS: all pipelined multipliers");$finish;end
    initial begin #1000000;$fatal(1,"multiplier timeout");end
endmodule
