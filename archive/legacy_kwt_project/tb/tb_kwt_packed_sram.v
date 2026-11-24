`timescale 1ns / 1ps
module packed_sram_case #(parameter DEPTH=128, parameter AW=$clog2(DEPTH))
    (output reg finished);
    reg clk=0, rst_n=0, wr=0;
    reg [AW-1:0] wa=0,ra=0;
    reg [31:0] wd=0;
    reg [7:0] mask=0;
    wire [31:0] rd;
    reg [31:0] refmem[0:DEPTH-1];
    integer i,n,seed=19283,errors=0;
    kwt_packed_sram #(.DW(32),.DEPTH(DEPTH)) dut
        (.clk(clk),.rst_n(rst_n),.wr(wr),.wa(wa),.wd(wd),.mask(mask),.ra(ra),.rd(rd));
    always #5 clk=~clk;
    task update(input integer addr,input [31:0] data,input [7:0] enables);
        begin
            @(negedge clk); wr=1; wa=addr; wd=data; mask=enables;
            for(n=0;n<8;n=n+1) if(enables[n]) refmem[addr][n*4 +: 4]=data[n*4 +: 4];
        end
    endtask
    initial begin
        finished=0;
        repeat(3) @(negedge clk); rst_n=1;
        for(i=0;i<DEPTH;i=i+1) update(i,$random(seed),8'hff);
        // Consecutive nibble/byte writes, A/B/A hazards and zero masks.
        for(i=0;i<4096;i=i+1) begin
            if(i<256) update(0,$random(seed),8'b1<<(i%8));
            else if(i<512) update(i%2,$random(seed),$random(seed));
            else update(($random(seed)&32'h7fffffff)%DEPTH,$random(seed),$random(seed));
        end
        @(negedge clk); wr=0;
        repeat(3) @(negedge clk);
        // Reset cancels pending updates but must not clear committed SRAM.
        rst_n=0; repeat(2) @(negedge clk); rst_n=1;
        for(i=0;i<DEPTH;i=i+1) begin
            @(negedge clk); ra=i;
            @(negedge clk);
            if(rd!==refmem[i]) begin
                errors=errors+1;
                if(errors<4) $display("MISMATCH SRAM depth=%0d addr=%0d got=%h expected=%h",DEPTH,i,rd,refmem[i]);
            end
        end
        if(errors) $fatal(1,"SRAM forwarding failed");
        $display("PASS: packed SRAM depth=%0d masked-write forwarding/reset",DEPTH);
        finished=1;
    end
endmodule
module tb_kwt_packed_sram;
    wire a,b,c;
    packed_sram_case #(.DEPTH(128)) t0(a);
    packed_sram_case #(.DEPTH(1024)) t1(b);
    packed_sram_case #(.DEPTH(4096)) t2(c);
    initial begin wait(a&&b&&c); $display("PASS: all SRAM shapes"); $finish; end
    initial begin #1000000; $fatal(1,"SRAM test timeout"); end
endmodule
