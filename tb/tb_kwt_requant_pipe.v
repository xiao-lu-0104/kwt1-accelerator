`timescale 1ns/1ps
module tb_kwt_requant_pipe;
    reg clk=0,rst_n=0,valid_in=0,wide_in=0;
    always #5 clk=~clk;
    reg signed [31:0] acc=0,bias=0,multiplier=0;
    wire valid_out;
    wire signed [15:0] quant;
    wire [7:0] gelu;
    kwt_requant_pipe dut(.*);
    reg signed [31:0] sum;
    reg signed [63:0] product,shifted;
    reg signed [15:0] expected;
    reg signed [8:0] index_sum;
    reg [7:0] idx;
    wire [7:0] lut;
    kwt_gelu_lut ref_lut(.idx(idx),.val(lut));
    always @* begin
        sum=acc+bias;
        product=sum*multiplier;
        shifted=(product+64'sd1073741824)>>>31;
        if(wide_in) expected=(shifted>32767)?32767:(shifted< -32767)?-32767:shifted[15:0];
        else expected=(shifted>127)?127:(shifted< -127)?-127:shifted[15:0];
        index_sum=$signed(expected[7:0])+9'sd127;
        idx=(index_sum<0)?0:(index_sum>254)?254:index_sum[7:0];
    end
    reg [11:0] vq=0;
    reg [15:0] qq[0:11];
    reg [7:0] gq[0:11];
    integer j,n,count=0;
    always @(posedge clk) begin
        if(!rst_n) vq=0;
        else begin
            vq={vq[10:0],valid_in};
            for(j=11;j>0;j=j-1) begin qq[j]=qq[j-1];gq[j]=gq[j-1];end
            qq[0]=expected;gq[0]=lut;
        end
        #1;
        if(valid_out!==vq[11]) $fatal(1,"requant valid mismatch");
        if(valid_out) begin
            if(quant!==qq[11]||gelu!==gq[11])
                $fatal(1,"requant mismatch got=%h/%h expected=%h/%h",quant,gelu,qq[11],gq[11]);
            count=count+1;
        end
    end
    initial begin
        repeat(3) @(negedge clk); rst_n=1;
        for(n=0;n<1200;n=n+1) begin
            @(negedge clk); valid_in=(n%7!=0);wide_in=n%2;
            acc=$random;bias=$random;multiplier=$random;
            if(n<8) begin
                acc=n[0]?32'h80000000:32'h7fffffff;
                bias=n[1]?32'h80000000:32'h7fffffff;
                multiplier=n[2]?32'h80000000:32'h7fffffff;
                valid_in=1;
            end
            if(n%5==0) begin acc=n-600;bias=0;multiplier=32'h7fffffff;end
            if(n==400) begin rst_n=0;valid_in=0;end
            if(n==402) rst_n=1;
        end
        @(negedge clk);valid_in=0;
        repeat(14) @(negedge clk);
        if(count<900) $fatal(1,"requant output count");
        $display("PASS: requant %0d random/boundary results, int8/int16, GELU, gaps/reset",count);
        $finish;
    end
endmodule
