`timescale 1ns/1ps
module tb_kwt_align_add_pipe;
    reg clk=0,rst_n=0,valid_in=0;
    always #5 clk=~clk;
    reg signed [7:0] a=0,b=0;
    reg signed [15:0] ma=0,mb=0;
    wire valid_out;
    wire signed [15:0] y,reference_y;
    kwt_align_add_pipe dut(.*);
    kwt_align_add ref_dut(.a(a),.b(b),.ma(ma),.mb(mb),.y(reference_y));
    reg [3:0] vq=0;
    reg [15:0] expected[0:3];
    integer n,j,count=0;
    always @(posedge clk) begin
        if(!rst_n) vq=0;
        else begin
            vq={vq[2:0],valid_in};
            for(j=3;j>0;j=j-1) expected[j]=expected[j-1];
            expected[0]=reference_y;
        end
        #1;
        if(valid_out!==vq[3]) $fatal(1,"align valid mismatch");
        if(valid_out) begin
            if(y!==expected[3]) $fatal(1,"align mismatch got=%h reference=%h",y,expected[3]);
            count=count+1;
        end
    end
    initial begin
        repeat(3) @(negedge clk);rst_n=1;
        for(n=0;n<1200;n=n+1) begin
            @(negedge clk);valid_in=(n%7!=0);a=$random;b=$random;ma=$random;mb=$random;
            if(n<16) begin
                a=n[0]?-128:127;b=n[1]?-128:127;
                ma=n[2]?-32768:32767;mb=n[3]?-32768:32767;valid_in=1;
            end
            if(n==400) begin rst_n=0;valid_in=0;end
            if(n==402) rst_n=1;
        end
        @(negedge clk);valid_in=0;repeat(6) @(negedge clk);
        if(count<900) $fatal(1,"align output count");
        $display("PASS: residual align %0d random/boundary results, gaps/reset",count);
        $finish;
    end
endmodule
