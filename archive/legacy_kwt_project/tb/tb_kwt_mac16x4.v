`timescale 1ns / 1ps
module tb_kwt_mac16x4;
    reg clk=0,rst_n=0,valid_in=0;
    reg [127:0] a=0,acc_in=0;
    reg [511:0] w=0;
    wire valid_out;
    wire [127:0] acc_out;
    reg [127:0] expected;
    reg [31:0] total;
    integer n,c,i,av,wv,seed=7319,errors=0;
    kwt_mac16x4 dut(.*);
    always #5 clk=~clk;
    initial begin
        repeat(3) @(negedge clk); rst_n=1;
        for(n=0;n<2000;n=n+1) begin
            @(negedge clk);
            valid_in=(n%7!=0);
            for(i=0;i<16;i=i+1) a[i*8 +: 8]=(n<4)?((n%2)?8'h80:8'h7f):$random(seed);
            for(i=0;i<64;i=i+1) w[i*8 +: 8]=(n<4)?((n<2)?8'h80:8'h7f):$random(seed);
            for(c=0;c<4;c=c+1) begin
                acc_in[c*32 +: 32]=(n<4)?32'h7fffffff:$random(seed);
                total=acc_in[c*32 +: 32];
                for(i=0;i<16;i=i+1) begin
                    av=$signed(a[i*8 +: 8]);
                    wv=$signed(w[(c*16+i)*8 +: 8]);
                    total=total+av*wv;
                end
                expected[c*32 +: 32]=total;
            end
            @(posedge clk); #1;
            if(valid_out!==valid_in||(valid_in&&acc_out!==expected)) errors=errors+1;
        end
        @(negedge clk); rst_n=0;
        @(posedge clk); #1;
        if(valid_out!==0||acc_out!==0) errors=errors+1;
        if(errors) $fatal(1,"MAC reference mismatches=%0d",errors);
        $display("PASS: shared MAC 2000 scalar-reference vectors, boundaries, wraparound, valid gaps and reset");
        $finish;
    end
endmodule
