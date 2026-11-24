`timescale 1ns / 1ps
module tb_kwt_mfcc_map;
    reg clk=0, rst_n=0, mf_we4=0;
    reg [9:0] mf_word_addr=0;
    reg [31:0] mf_data32=0;
    wire [31:0] act_rd_data;
    reg [10:0] act_rd_addr=0;
    always #5 clk=~clk;

    kwt_top dut (
        .clk(clk), .rst_n(rst_n), .start(1'b0),
        .mf_we(1'b0), .mf_addr(13'd0), .mf_data(8'd0),
        .mf_we4(mf_we4), .mf_word_addr(mf_word_addr), .mf_data32(mf_data32),
        .act_rd_addr(act_rd_addr), .act_rd_data(act_rd_data),
        .pp_wgt_we(1'b0), .pp_wgt_addr(12'd0), .pp_wgt_data(4'd0),
        .pp_bp_we(1'b0), .pp_bp_addr(6'd0), .pp_bp_bias(32'sd0), .pp_bp_m(32'sd0),
        .cp_we(1'b0), .cp_addr(13'd0), .cp_data(8'd0),
        .rom_wgt(4'd0), .rom_wgt16(64'd0), .rom_bias(32'sd0), .rom_m(32'sd0),
        .rom_ln_gamma(16'sd0), .rom_ln_beta(16'sd0),
        .hd_wgt_we(1'b0), .hd_wgt_addr(10'd0), .hd_wgt_data(4'd0),
        .hd_bp_we(1'b0), .hd_bp_addr(4'd0), .hd_bp_bias(32'sd0), .hd_bp_m(32'sd0),
        .pred_class(), .done(), .cycle_count()
    );

    initial begin
        repeat(2) @(negedge clk); rst_n=1;
        @(negedge clk); mf_we4=1; mf_word_addr=9; mf_data32=32'h44332211;
        @(negedge clk); mf_word_addr=10; mf_data32=32'h88776655;
        @(negedge clk); mf_we4=0;
        if (dut.act_buf[36] !== 8'h11 || dut.act_buf[37] !== 8'h22 ||
            dut.act_buf[38] !== 8'h33 || dut.act_buf[39] !== 8'h44 ||
            dut.act_buf[64] !== 8'h55 || dut.act_buf[65] !== 8'h66 ||
            dut.act_buf[66] !== 8'h77 || dut.act_buf[67] !== 8'h88)
            $fatal(1,"MFCC packed-byte to padded-token mapping failed");
        $display("PASS: packed MFCC maps 40-byte rows into 64-byte token stride");
        $finish;
    end
endmodule
