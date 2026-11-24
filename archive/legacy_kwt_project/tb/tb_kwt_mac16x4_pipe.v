`timescale 1ns/1ps
module tb_kwt_mac16x4_pipe;
    reg clk=0,rst_n=0,valid_in=0,first_in=0;
    always #5 clk=~clk;
    reg [127:0] a=0;
    reg [511:0] w=0;
    wire valid_out;
    wire [127:0] acc_out;
    kwt_mac16x4_pipe dut(.*);
    reg [6:0] vq=0;
    reg [127:0] expected[0:6];
    reg signed [31:0] acc[0:3];
    reg signed [31:0] dot;
    integer n,c,i,j,count=0,segments=0;
    always @(posedge clk) begin
        if(!rst_n) begin vq=0;for(c=0;c<4;c=c+1) acc[c]=0;end
        else begin
            for(j=6;j>0;j=j-1) expected[j]=expected[j-1];
            vq={vq[5:0],valid_in};
            if(valid_in) for(c=0;c<4;c=c+1) begin
                dot=0;
                for(i=0;i<16;i=i+1) dot=dot+$signed(a[i*8 +: 8])*$signed(w[(c*16+i)*8 +: 8]);
                acc[c]=(first_in?32'sd0:acc[c])+dot;
                expected[0][c*32 +: 32]=acc[c];
            end
        end
        #1;
        if(valid_out!==vq[6]) $fatal(1,"MAC valid mismatch");
        if(valid_out) begin
            if(acc_out!==expected[6]) $fatal(1,"MAC result mismatch got=%h expected=%h",acc_out,expected[6]);
            count=count+1;
        end
    end
    initial begin
        repeat(3) @(negedge clk);rst_n=1;
        for(n=0;n<1200;n=n+1) begin
            @(negedge clk);valid_in=(n%9!=0);first_in=(segments%16==0);
            for(j=0;j<4;j=j+1) a[j*32 +: 32]=$random;
            for(j=0;j<16;j=j+1) w[j*32 +: 32]=$random;
            if(n<32) begin a=(n%2)?{16{8'h80}}:{16{8'h7f}};w=(n%3)?{64{8'h80}}:{64{8'h7f}};end
            if(valid_in) segments=segments+1;
            if(n==400) begin rst_n=0;valid_in=0;segments=0;end
            if(n==402) begin rst_n=1;first_in=1;end
        end
        @(negedge clk);valid_in=0;
        repeat(9) @(negedge clk);
        if(count<900) $fatal(1,"MAC output count");
        $display("PASS: MAC %0d four-channel results, consecutive segments, first tags, gaps/reset",count);
        $finish;
    end
endmodule
