`timescale 1ns / 1ps
// Adapter test: independent simultaneous ports, bank-boundary read latency,
// and no output change when just the combinational read address changes.
module foundry_sram_case #(parameter DEPTH=1024, parameter AW=$clog2(DEPTH))
    (output reg finished);
    reg clk=0, we=0;
    reg [AW-1:0] wa=0, ra=0;
    reg [15:0] wd=0;
    wire [15:0] rd;
    reg [15:0] reference[0:DEPTH-1];
    reg [15:0] held;
    integer i, addr, waddr, seed=64913;
    kwt_mem16 #(.DEPTH(DEPTH)) dut
        (.clk(clk),.we(we),.wa(wa),.wd(wd),.ra(ra),.rd(rd));
    always #5 clk=~clk;
    initial begin
        finished=0;
        for(i=0;i<DEPTH;i=i+1) begin
            @(negedge clk); we=1; wa=i; wd=$random(seed);
            ra=(i+DEPTH/2)%DEPTH;
            reference[i]=wd;
        end
        @(negedge clk); we=0;
        // Alternate across all four physical banks and boundary addresses.
        // Adjacent bank-address changes must wait for the next rising edge.
        for(i=0;i<2048;i=i+1) begin
            @(negedge clk);
            held=rd;
            if (DEPTH==4096)
                addr=((i%4)*1024 + ((i/4)%2 ? 1023 : 0));
            else addr=($random(seed)&32'h7fffffff)%DEPTH;
            ra=addr;
            // A simultaneous write to another address must not steal the read.
            waddr=(addr+DEPTH/2+1)%DEPTH;
            we=1; wa=waddr; wd=$random(seed); reference[waddr]=wd;
            #1;
            if(rd!==held) $fatal(1,"Depth %0d: read address changed output before clock",DEPTH);
            @(posedge clk); #4;
            if(rd!==reference[addr])
                $fatal(1,"Depth %0d addr %0d: got %h expected %h",DEPTH,addr,rd,reference[addr]);
        end
        @(negedge clk); we=0;
        for(i=0;i<DEPTH;i=i+1) begin
            @(negedge clk); ra=i;
            @(posedge clk); #4;
            if(rd!==reference[i]) $fatal(1,"Depth %0d final read mismatch at %0d",DEPTH,i);
        end
        finished=1;
        $display("PASS: foundry adapter depth=%0d independent ports / bank boundary / read latency",DEPTH);
    end
endmodule

module tb_kwt_foundry_sram16;
    wire a,b,c;
    foundry_sram_case #(.DEPTH(128)) t0(a);
    foundry_sram_case #(.DEPTH(1024)) t1(b);
    foundry_sram_case #(.DEPTH(4096)) t2(c);
    initial begin wait(a&&b&&c); $display("PASS: all foundry adapter shapes"); $finish; end
    initial begin #1000000; $fatal(1,"Adapter test timeout"); end
endmodule
