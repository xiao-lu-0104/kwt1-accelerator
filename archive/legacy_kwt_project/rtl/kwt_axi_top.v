`timescale 1ns / 1ps
// AXI4-Lite integration shell. Parameter storage remains on the platform side.
module kwt_axi_top (
    input wire aclk, input wire aresetn,
    input wire [15:0] awaddr, input wire awvalid, output wire awready,
    input wire [31:0] wdata, input wire [3:0] wstrb, input wire wvalid,
    output wire wready, output wire [1:0] bresp, output wire bvalid, input wire bready,
    input wire [15:0] araddr, input wire arvalid, output wire arready,
    output wire [31:0] rdata, output wire [1:0] rresp, output wire rvalid, input wire rready,
    input wire pp_wgt_we, input wire [11:0] pp_wgt_addr, input wire [3:0] pp_wgt_data,
    input wire pp_bp_we, input wire [5:0] pp_bp_addr,
    input wire signed [31:0] pp_bp_bias, input wire signed [31:0] pp_bp_m,
    input wire cp_we, input wire [12:0] cp_addr, input wire [7:0] cp_data,
    output wire [3:0] cur_layer, output wire [3:0] ld_sel, output wire [13:0] ld_addr,
    input wire [3:0] rom_wgt, input wire [63:0] rom_wgt16,
    input wire signed [31:0] rom_bias, input wire signed [31:0] rom_m,
    input wire signed [15:0] rom_ln_gamma, input wire signed [15:0] rom_ln_beta,
    input wire hd_wgt_we, input wire [9:0] hd_wgt_addr, input wire [3:0] hd_wgt_data,
    input wire hd_bp_we, input wire [3:0] hd_bp_addr,
    input wire signed [31:0] hd_bp_bias, input wire signed [31:0] hd_bp_m
);
    wire start, soft_rst, busy, done;
    wire [3:0] pred;
    wire [31:0] cycles;
    wire [9:0] mfcc_addr;
    wire [31:0] mfcc_data, act_data;
    wire mfcc_we;
    wire [10:0] frame_count, act_addr;
    reg busy_r;
    wire core_rst_n = aresetn & ~soft_rst;

    assign busy = busy_r;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) busy_r <= 1'b0;
        else if (soft_rst) busy_r <= 1'b0;
        else if (start) busy_r <= 1'b1;
        else if (done) busy_r <= 1'b0;
    end

    kwt_axi_slave u_axi (
        .aclk(aclk), .aresetn(aresetn),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .start(start), .soft_rst(soft_rst), .busy(busy), .done_in(done),
        .pred(pred), .cycles(cycles), .mfcc_addr(mfcc_addr),
        .mfcc_data(mfcc_data), .mfcc_we(mfcc_we), .frame_count(frame_count),
        .act_rd_addr(act_addr), .act_rd_data(act_data)
    );

    kwt_top u_core (
        .clk(aclk), .rst_n(core_rst_n), .start(start),
        .mf_we(1'b0), .mf_addr(13'd0), .mf_data(8'd0),
        .mf_we4(mfcc_we), .mf_word_addr(mfcc_addr), .mf_data32(mfcc_data),
        .act_rd_addr(act_addr), .act_rd_data(act_data),
        .pp_wgt_we(pp_wgt_we), .pp_wgt_addr(pp_wgt_addr), .pp_wgt_data(pp_wgt_data),
        .pp_bp_we(pp_bp_we), .pp_bp_addr(pp_bp_addr),
        .pp_bp_bias(pp_bp_bias), .pp_bp_m(pp_bp_m),
        .cp_we(cp_we), .cp_addr(cp_addr), .cp_data(cp_data),
        .cur_layer(cur_layer), .ld_sel(ld_sel), .ld_addr(ld_addr),
        .rom_wgt(rom_wgt), .rom_wgt16(rom_wgt16), .rom_bias(rom_bias), .rom_m(rom_m),
        .rom_ln_gamma(rom_ln_gamma), .rom_ln_beta(rom_ln_beta),
        .hd_wgt_we(hd_wgt_we), .hd_wgt_addr(hd_wgt_addr), .hd_wgt_data(hd_wgt_data),
        .hd_bp_we(hd_bp_we), .hd_bp_addr(hd_bp_addr),
        .hd_bp_bias(hd_bp_bias), .hd_bp_m(hd_bp_m),
        .pred_class(pred), .done(done), .cycle_count(cycles)
    );
endmodule
