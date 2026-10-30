`timescale 1ns / 1ps
// Run against REAL foundry models with specify checks enabled. Drive A inputs
// away from its active edge; the adapter stages B inputs for the half cycle.
// The ideal full-encoder regression separately disables pin setup/hold checks.
module sram_phase_case #(parameter DEPTH=128, parameter AW=$clog2(DEPTH))
    (output reg finished);
    reg clk=0, we=0;
    reg [AW-1:0] wa=0, ra=0;
    reg [15:0] wd=0;
    wire [15:0] rd;
    reg [15:0] reference[0:DEPTH-1];
    reg [15:0] expected;
    integer i, address, seed=92031;
    kwt_mem16 #(.DEPTH(DEPTH)) dut
        (.clk(clk),.we(we),.wa(wa),.wd(wd),.ra(ra),.rd(rd));
    // 6.667 ns period; half cycles round to 3.333/3.334 ns at 1 ps precision.
    always begin #3.333 clk=1; #3.334 clk=0; end
    task transaction(input integer read_addr, input integer write_addr,
                     input bit enable, input [15:0] data, input bit check_read);
        begin
            @(negedge clk); #0.8;
            ra=read_addr; wa=write_addr; we=enable; wd=data;
            expected=reference[read_addr];
            @(posedge clk);
            // Change live write signals before B fires. Captured address,
            // data AND enable must win, including the high bank-address bits.
            #1; wa=(write_addr+DEPTH/2+1)%DEPTH; wd=~data; we=~enable;
            #1;
            if(check_read && rd !== expected)
                $fatal(1,"Phase depth=%0d read=%0d got=%h expected=%h",DEPTH,read_addr,rd,expected);
            if(enable) reference[write_addr]=data;
        end
    endtask
    initial begin
        finished=0;
        for(i=0;i<DEPTH;i=i+1) transaction(i,i,1,$random(seed),0);
        // Repeated same-word and adjacent-word accesses also exercise any
        // physical row shared by column-multiplexed logical addresses.
        for(i=0;i<256;i=i+1) begin
            address=(i/8)%DEPTH;
            transaction(address,address,1,$random(seed),1);
            transaction(address,address^1,1,$random(seed),1);
            transaction(address^1,address,0,16'hdead,1);
        end
        for(i=0;i<DEPTH;i=i+1) transaction(i,(i+1)%DEPTH,0,0,1);
        // Drain the final accepted transaction before declaring completion.
        @(negedge clk); #0.8; we=0;
        $display("PASS: phase depth=%0d 150MHz same-word / same-row / captured write / bank decode",DEPTH);
        finished=1;
    end
endmodule

module sram_phase_reset_case(output reg finished);
    reg clk=0, rst_n=0, wr=0;
    reg [6:0] wa=0, ra=0;
    reg [31:0] wd=0;
    reg [7:0] mask=0;
    wire [31:0] rd;
    always begin #3.333 clk=1; #3.334 clk=0; end
    kwt_packed_sram #(.DW(32),.DEPTH(128)) dut
        (.clk(clk),.rst_n(rst_n),.wr(wr),.wa(wa),.wd(wd),.mask(mask),.ra(ra),.rd(rd));
    initial begin
        finished=0;
        repeat(2) @(negedge clk);
        #0.8; rst_n=1; wr=1; mask=8'hff; wd=32'h12345678;
        @(negedge clk); #0.8; wr=0;
        repeat(4) @(negedge clk);
        #0.8; wr=1; wd=32'habcdefff;
        @(negedge clk); #0.8; wr=0;
        // The next posedge accepts the packed RMW write into the adapter.
        // Reset after acceptance must not cancel its following B-clock commit.
        @(posedge clk); #1; rst_n=0;
        repeat(2) @(negedge clk); #0.8; rst_n=1;
        @(posedge clk); #2;
        if(rd !== 32'habcdefff) $fatal(1,"Phase reset cancelled an accepted write: %h",rd);
        $display("PASS: phase reset between write acceptance and physical commit");
        finished=1;
    end
endmodule

module tb_kwt_sram_phase;
    wire a,b,c,d;
    sram_phase_case #(.DEPTH(128)) t0(a);
    sram_phase_case #(.DEPTH(1024)) t1(b);
    sram_phase_case #(.DEPTH(4096)) t2(c);
    sram_phase_reset_case t3(d);
    initial begin wait(a&&b&&c&&d); $display("PASS: split-phase SRAM contract at 150MHz"); $finish; end
    initial begin #1000000; $fatal(1,"Phase SRAM test timeout"); end
endmodule
