`timescale 1ns / 1ps
// Competition encoder task boundary; the original MFCC/classifier demo shell
// remains separate. This port list matches the E203 example AXI peripheral.
module kwt_encoder_axi_top (
    input wire clk,rst_n,
    input wire axi_awvalid,output wire axi_awready,input wire [31:0] axi_awaddr,
    input wire [3:0] axi_awcache,input wire [2:0] axi_awprot,
    input wire [1:0] axi_awlock,axi_awburst,input wire [3:0] axi_awlen,input wire [2:0] axi_awsize,
    input wire axi_wvalid,output wire axi_wready,input wire [31:0] axi_wdata,
    input wire [3:0] axi_wstrb,input wire axi_wlast,
    output wire axi_bvalid,input wire axi_bready,output wire [1:0] axi_bresp,
    input wire axi_arvalid,output wire axi_arready,input wire [31:0] axi_araddr,
    input wire [3:0] axi_arcache,input wire [2:0] axi_arprot,
    input wire [1:0] axi_arlock,axi_arburst,input wire [3:0] axi_arlen,input wire [2:0] axi_arsize,
    output wire axi_rvalid,input wire axi_rready,output wire [31:0] axi_rdata,
    output wire [1:0] axi_rresp,output wire axi_rlast
);
    wire core_rst_n,core_start,x_we,param_valid,param_ready,core_out_we,core_done;
    wire [12:0] x_addr,core_out_addr;
    wire [7:0] x_data,core_out_data;
    wire [63:0] param_data;
    wire [3:0] cur_layer,ld_sel;
    wire [13:0] ld_addr;
    wire [31:0] core_cycles;
    kwt_encoder_mmio u_mmio(.*);
    kwt_encoder_12 #(.PARAM_HANDSHAKE(1)) u_encoder(
        .clk(clk),.rst_n(core_rst_n),.start(core_start),.x_we(x_we),.x_addr(x_addr),.x_data(x_data),
        .param_valid(param_valid),.param_ready(param_ready),.cur_layer(cur_layer),.ld_sel(ld_sel),.ld_addr(ld_addr),
        .rom_wgt(param_data[3:0]),.rom_wgt16(param_data),.rom_bias(param_data[31:0]),.rom_m(param_data[63:32]),
        .rom_ln_gamma(param_data[15:0]),.rom_ln_beta(param_data[31:16]),
        .out_we(core_out_we),.out_addr(core_out_addr),.out_data(core_out_data),.done(core_done),.cycle_count(core_cycles));
endmodule
