`timescale 1ns / 1ps
module tb_kwt_axi_top_load;
    reg clk=0, rst_n=0;
    reg [15:0] awaddr=0;
    reg awvalid=0;
    wire awready;
    reg [31:0] wdata=0;
    reg [3:0] wstrb=4'hf;
    reg wvalid=0;
    wire wready;
    wire [1:0] bresp;
    wire bvalid;
    reg bready=1;
    reg [15:0] araddr=0;
    reg arvalid=0;
    wire arready;
    wire [31:0] rdata;
    wire [1:0] rresp;
    wire rvalid;
    reg rready=1;
    wire [3:0] cur_layer, ld_sel;
    wire [13:0] ld_addr;
    always #5 clk=~clk;

    kwt_axi_top dut (
        .aclk(clk), .aresetn(rst_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .pp_wgt_we(1'b0), .pp_wgt_addr(12'd0), .pp_wgt_data(4'd0),
        .pp_bp_we(1'b0), .pp_bp_addr(6'd0), .pp_bp_bias(32'sd0), .pp_bp_m(32'sd0),
        .cp_we(1'b0), .cp_addr(13'd0), .cp_data(8'd0),
        .cur_layer(cur_layer), .ld_sel(ld_sel), .ld_addr(ld_addr),
        .rom_wgt(4'd0), .rom_wgt16(64'd0), .rom_bias(32'sd0), .rom_m(32'sd0),
        .rom_ln_gamma(16'sd0), .rom_ln_beta(16'sd0),
        .hd_wgt_we(1'b0), .hd_wgt_addr(10'd0), .hd_wgt_data(4'd0),
        .hd_bp_we(1'b0), .hd_bp_addr(4'd0), .hd_bp_bias(32'sd0), .hd_bp_m(32'sd0)
    );

    task write32(input [15:0] address, input [31:0] value);
    begin
        @(negedge clk); awaddr=address; awvalid=1;
        @(posedge clk); while (!awready) @(posedge clk);
        @(negedge clk); awvalid=0; wdata=value; wvalid=1;
        @(posedge clk); while (!wready) @(posedge clk);
        @(negedge clk); wvalid=0;
        while (!bvalid) @(posedge clk);
        if (bresp != 0) $fatal(1,"AXI write response error");
        @(negedge clk);
    end endtask

    initial begin
        repeat(3) @(negedge clk); rst_n=1;
        write32(16'h0100,32'h44332211);
        write32(16'h0128,32'h88776655); // word 10 starts token 1
        if (dut.u_core.act_buf[0] !== 8'h11 || dut.u_core.act_buf[1] !== 8'h22 ||
            dut.u_core.act_buf[2] !== 8'h33 || dut.u_core.act_buf[3] !== 8'h44 ||
            dut.u_core.act_buf[64] !== 8'h55 || dut.u_core.act_buf[65] !== 8'h66 ||
            dut.u_core.act_buf[66] !== 8'h77 || dut.u_core.act_buf[67] !== 8'h88)
            $fatal(1,"AXI MFCC writes did not reach core input buffer");
        $display("PASS: AXI MFCC writes reach kwt_top with correct 40-to-64 stride");
        $finish;
    end
endmodule
