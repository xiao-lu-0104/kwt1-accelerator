`timescale 1ns/1ps
// Compare retimed LayerNorm against the pre-output-pipeline implementation.
module tb_kwt_layernorm_pipe;
    localparam ROWS=12, TOTAL=64*ROWS;
    reg clk=0,rst_n=0,start=0,in_we=0,gp_we=0;
    always #5 clk=~clk;
    reg [12:0] in_addr=0;
    reg signed [15:0] in_data=0,gp_gamma=0,gp_beta=0;
    reg [5:0] gp_addr=0;
    reg [31:0] eps_q=0;
    wire [1:0] we,done;
    wire [12:0] addr[0:1];
    wire [7:0] data[0:1];
    wire [31:0] cycles[0:1];
    kwt_layernorm #(.ROWS(ROWS)) dut(
        .clk(clk),.rst_n(rst_n),.start(start),.in_we(in_we),.in_addr(in_addr),.in_data(in_data),
        .gp_we(gp_we),.gp_addr(gp_addr),.gp_gamma(gp_gamma),.gp_beta(gp_beta),.eps_q(eps_q),
        .out_we(we[0]),.out_addr(addr[0]),.out_data(data[0]),.done(done[0]),.cycle_count(cycles[0]));
    kwt_layernorm_pre_output_pipe #(.ROWS(ROWS)) ref_dut(
        .clk(clk),.rst_n(rst_n),.start(start),.in_we(in_we),.in_addr(in_addr),.in_data(in_data),
        .gp_we(gp_we),.gp_addr(gp_addr),.gp_gamma(gp_gamma),.gp_beta(gp_beta),.eps_q(eps_q),
        .out_we(we[1]),.out_addr(addr[1]),.out_data(data[1]),.done(done[1]),.cycle_count(cycles[1]));
    reg [7:0] result0[0:TOTAL-1],result1[0:TOTAL-1];
    integer count0=0,count1=0,i,test,timeout,errors=0;
    always @(negedge clk) if(rst_n) begin
        if(we[0]) begin
            if(addr[0] !== count0) $fatal(1,"output order DUT");
            result0[addr[0]]=data[0]; count0=count0+1;
        end
        if(we[1]) begin
            if(addr[1] !== count1) $fatal(1,"output order reference");
            result1[addr[1]]=data[1]; count1=count1+1;
        end
    end
    initial begin
        repeat(3) @(negedge clk); rst_n=1;
        for(test=0;test<4;test=test+1) begin
            for(i=0;i<64;i=i+1) begin
                @(negedge clk); gp_we=1; gp_addr=i;
                case(i%4)
                    0: begin gp_gamma=-32768; gp_beta=-32768; end
                    1: begin gp_gamma=32767; gp_beta=32767; end
                    2: begin gp_gamma=0; gp_beta=0; end
                    3: begin gp_gamma=$random; gp_beta=$random; end
                endcase
            end
            @(negedge clk); gp_we=0;
            for(i=0;i<TOTAL;i=i+1) begin
                @(negedge clk); in_we=1; in_addr=i;
                case(i/64)
                    0: in_data=-32768;
                    1: in_data=32767;
                    2: in_data=(i%64==0)?32767:-32768;
                    3: in_data=(i%64==0)?-32768:32767;
                    4: in_data=(i%2)?-32768:32767;
                    5: in_data=0;
                    6: in_data=(i%2)?-1:1;
                    default: in_data=$random;
                endcase
            end
            @(negedge clk); in_we=0; eps_q=(test==0)?0:(test==1)?1:(test==2)?32'h7fffffff:32'hffffffff;
            count0=0; count1=0; start=1; timeout=0;
            while(done!==2'b11 && timeout<100000) begin @(negedge clk); timeout=timeout+1; end
            if(done!==2'b11 || count0!=TOTAL || count1!=TOTAL) $fatal(1,"LN timeout/count");
            for(i=0;i<TOTAL;i=i+1) if(result0[i] !== result1[i]) begin
                if(errors<10) $display("MISMATCH case=%0d addr=%0d got=%h ref=%h",test,i,result0[i],result1[i]);
                errors=errors+1;
            end
            start=0; repeat(4) @(negedge clk);
        end
        if(errors) $fatal(1,"LN differential %0d mismatches",errors);
        $display("PASS: LN differential 3072 outputs, extremes, variance overflow, eps, repeated start");
        $finish;
    end
endmodule
