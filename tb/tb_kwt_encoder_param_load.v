`timescale 1ns / 1ps
// Real encoder and SRAM datapath; checks parameter scan/acceptance only and
// stops when compute starts. Full golden compute is a separate regression.
module encoder_param_case #(parameter HANDSHAKE=1)(output reg finished);
    reg clk=0,rst_n=0,start=0,s_valid=0;
    wire s_ready,p_valid,p_ready,stream_empty;
    wire [63:0] stream_data;
    integer sent_words=0,accepted=0,waits=0,seed=7133;
    wire [63:0] record_data;
    wire [3:0] cur_layer,ld_sel;
    wire [13:0] ld_addr;
    wire done,out_we;
    wire [12:0] out_addr;
    wire [7:0] out_data;
    wire [31:0] cycle_count;
    reg [149:0] frozen;
    reg was_stalled=0;
    reg source_accepted=0;
    integer expected_sel,expected_addr,index;
    function [63:0] record_value(input integer number);
        record_value={32'h01000000+number,32'h02000000+number};
    endfunction
    wire [63:0] next_record=record_value(sent_words/2);
    wire [31:0] s_data=sent_words[0]?next_record[63:32]:next_record[31:0];
    kwt_param_stream stream(.clk(clk),.rst_n(rst_n),.s_valid(s_valid),.s_ready(s_ready),
        .s_data(s_data),.m_valid(p_valid),.m_ready(p_ready),.m_data(stream_data),.empty(stream_empty));
    wire valid=HANDSHAKE?p_valid:1'b1;
    // Invalid data is poison, so freezing only the address cannot pass.
    assign record_data=HANDSHAKE?(p_valid?stream_data:64'hxxxxxxxxxxxxxxxx):record_value(accepted);
    kwt_encoder_12 #(.NLAYER(1),.PARAM_HANDSHAKE(HANDSHAKE)) dut(
        .clk(clk),.rst_n(rst_n),.start(start),.x_we(1'b0),.x_addr(13'd0),.x_data(8'd0),
        .cur_layer(cur_layer),.ld_sel(ld_sel),.ld_addr(ld_addr),
        .rom_wgt(record_data[3:0]),.rom_wgt16(record_data),
        .rom_bias(record_data[31:0]),.rom_m(record_data[63:32]),
        .rom_ln_gamma(record_data[15:0]),.rom_ln_beta(record_data[31:16]),
        .param_valid(valid),.param_ready(p_ready),
        .out_we(out_we),.out_addr(out_addr),.out_data(out_data),.done(done),.cycle_count(cycle_count));
    always #5 clk=~clk;
    always @(negedge clk) begin
        if(!rst_n) s_valid=0;
        else if(!s_valid || source_accepted) s_valid=HANDSHAKE && sent_words<7564 && (($random(seed)&7)>2);
    end
    always @(posedge clk) begin
        if(!rst_n) begin sent_words<=0; accepted<=0; waits=0; was_stalled=0; source_accepted<=0; end
        else begin
            source_accepted<=s_valid&&s_ready;
            if(HANDSHAKE && s_valid&&s_ready) sent_words<=sent_words+1;
            if(was_stalled && {cur_layer,ld_sel,ld_addr,dut.m_score_r,dut.m_ctx_r,
                               dut.ma1_r,dut.mb1_r,dut.ma2_r,dut.mb2_r}!==frozen)
                $fatal(1,"Parameter address/constants changed during stall");
            was_stalled=HANDSHAKE && p_ready && !p_valid;
            frozen={cur_layer,ld_sel,ld_addr,dut.m_score_r,dut.m_ctx_r,
                    dut.ma1_r,dut.mb1_r,dut.ma2_r,dut.mb2_r};
            if(was_stalled) begin
                waits=waits+1;
                if(dut.ld_wgt || dut.ld_bp || dut.ld_ln)
                    $fatal(1,"Invalid parameter asserted a destination write");
            end
            if(dut.loading && (!HANDSHAKE || (p_ready&&p_valid))) begin
                index=accepted;
                if(index<1024) begin expected_sel=index/256; expected_addr=(index%256)*16; end
                else if(index<3072) begin expected_sel=4+(index-1024)/1024; expected_addr=((index-1024)%1024)*16; end
                else if(index<3264) begin expected_sel=6; expected_addr=index-3072; end
                else if(index<3328) begin expected_sel=7; expected_addr=index-3264; end
                else if(index<3584) begin expected_sel=8; expected_addr=index-3328; end
                else if(index<3648) begin expected_sel=9; expected_addr=index-3584; end
                else if(index<3776) begin expected_sel=10; expected_addr=index-3648; end
                else begin expected_sel=12; expected_addr=index-3776; end
                if(cur_layer!==0 || ld_sel!==expected_sel || ld_addr!==expected_addr || record_data!==record_value(index))
                    $fatal(1,"Parameter handshake=%0d record=%0d selector=%0d addr=%0d payload=%h",HANDSHAKE,index,ld_sel,ld_addr,record_data);
                accepted<=accepted+1;
            end
        end
    end
    initial begin
        finished=0;
        repeat(3) @(negedge clk); rst_n=1; start=1;
        wait(accepted==7); @(negedge clk); rst_n=0; start=0;
        repeat(3) @(negedge clk); rst_n=1; start=1;
        wait(dut.enc_start); @(negedge clk);
        if(accepted!=3782 || (HANDSHAKE && (sent_words!=7564 || waits==0 || !stream_empty)))
            $fatal(1,"Parameter scan failed to drain before compute");
        if(dut.m_score_r!==32'h01000ec0 || dut.m_ctx_r!==32'h01000ec1 ||
           dut.ma1_r!==16'h0ec2 || dut.mb1_r!==16'h0ec3 || dut.ma2_r!==16'h0ec4 || dut.mb2_r!==16'h0ec5)
            $fatal(1,"Layer constants did not latch accepted records");
        $display("PASS: encoder parameter handshake=%0d 3782 records / all selectors / reset / stalls=%0d",HANDSHAKE,waits);
        finished=1;
    end
endmodule
module tb_kwt_encoder_param_load;
    wire a,b;
    encoder_param_case #(.HANDSHAKE(0)) t0(a);
    encoder_param_case #(.HANDSHAKE(1)) t1(b);
    initial begin wait(a&&b); $display("PASS: encoder parameter loading contract"); $finish; end
    initial begin #1000000; $fatal(1,"Encoder parameter loading timeout"); end
endmodule
