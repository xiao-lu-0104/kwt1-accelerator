`timescale 1ns / 1ps
// AXI4-Lite slave wrapper for the KWT-1 accelerator.
//
// Register map (32-bit aligned, byte addresses):
//   0x000  CTRL        W  bit0 = start (self-clearing), bit1 = soft reset
//   0x004  STATUS      R  bit0 = busy, bit1 = done
//   0x008  PRED        R  [3:0] predicted class
//   0x00C  CYCLES      R  cycle count of the last inference
//   0x010  NFRAMES     R  number of accepted MFCC word writes
//   0x100 + 4*i  MFCC   W  four MFCC bytes packed little endian, i = 0..979
//   0x800 + 4*i  ACT    R  four activation bytes of the last layer output
//
// MFCC accepts 980 aligned full-word writes (98 x 40 = 3920 bytes).
// ACT reads use a relative 11-bit index covering all 1584 output words.
module kwt_axi_slave #(
    parameter AW = 16,
    parameter DW = 32,
    parameter MW = 10            // MFCC word index width (980 words)
)(
    // ------------------------------------------------------------------
    // AXI4-Lite
    // ------------------------------------------------------------------
    input  wire            aclk,
    input  wire            aresetn,

    input  wire [AW-1:0]   awaddr,
    input  wire            awvalid,
    output wire            awready,

    input  wire [DW-1:0]   wdata,
    input  wire [DW/8-1:0] wstrb,
    input  wire            wvalid,
    output wire            wready,

    output wire [1:0]      bresp,
    output wire            bvalid,
    input  wire            bready,

    input  wire [AW-1:0]   araddr,
    input  wire            arvalid,
    output wire            arready,

    output wire [DW-1:0]   rdata,
    output wire [1:0]      rresp,
    output wire            rvalid,
    input  wire            rready,

    // ------------------------------------------------------------------
    // accelerator side
    // ------------------------------------------------------------------
    output reg             start,
    output reg             soft_rst,

    input  wire            busy,
    input  wire            done_in,
    input  wire [3:0]      pred,
    input  wire [31:0]     cycles,

    // MFCC write port (one word per accepted write)
    output reg  [MW-1:0]   mfcc_addr,
    output reg  [31:0]     mfcc_data,
    output reg             mfcc_we,
    output reg  [MW:0]     frame_count,

    // activation read port
    output wire [10:0]     act_rd_addr,
    input  wire [31:0]     act_rd_data
);

    // ------------------------------------------------------------------
    // write channel
    // ------------------------------------------------------------------
    localparam S_W_IDLE = 2'd0;
    localparam S_W_DATA = 2'd1;
    localparam S_W_RESP = 2'd2;

    reg [1:0]   wstate;
    reg [AW-1:0] waddr_r;

    assign awready = (wstate == S_W_IDLE);
    assign wready  = (wstate == S_W_DATA);
    assign bvalid  = (wstate == S_W_RESP);
    reg [1:0] bresp_r;
    assign bresp = bresp_r;

    wire wr_ctrl   = (waddr_r[15:0] == 16'h0000);
    wire wr_mfcc   = (waddr_r >= 16'h0100 && waddr_r < 16'h1050); // 980 words
    wire [MW-1:0] mfcc_idx = (waddr_r - 16'h0100) >> 2;   // 0x100 / 4

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            bresp_r    <= 2'b00;
            wstate     <= S_W_IDLE;
            waddr_r    <= {AW{1'b0}};
            start      <= 1'b0;
            soft_rst   <= 1'b0;
            mfcc_we    <= 1'b0;
            mfcc_addr  <= {MW{1'b0}};
            mfcc_data  <= 32'd0;
            frame_count<= {(MW+1){1'b0}};
        end else begin
            mfcc_we  <= 1'b0;
            start    <= 1'b0;
            soft_rst <= 1'b0;
            case (wstate)
                S_W_IDLE: begin
                    if (awvalid) begin
                        waddr_r <= awaddr;
                        wstate  <= S_W_DATA;
                    end
                end
                S_W_DATA: begin
                    if (wvalid) begin
                        bresp_r <= 2'b00;
                        if (waddr_r[1:0] != 0) begin
                            bresp_r <= 2'b10; // unaligned access
                        end else if (wstrb == 0) begin
                            // AXI permits a write with no enabled bytes.
                        end else if (wr_ctrl) begin
                            start    <= wstrb[0] && wdata[0];
                            soft_rst <= wstrb[0] && wdata[1];
                            if (wstrb[0] && wdata[1]) frame_count <= 0;
                        end else if (wr_mfcc && wstrb == 4'hf) begin
                            mfcc_addr <= mfcc_idx;
                            mfcc_data <= wdata;
                            mfcc_we   <= 1'b1;
                            frame_count <= frame_count + {{MW{1'b0}}, 1'b1};
                        end else begin
                            // Downstream has no byte enables: reject partial writes.
                            bresp_r <= 2'b10;
                        end
                        wstate <= S_W_RESP;
                    end
                end
                S_W_RESP: begin
                    if (bready) wstate <= S_W_IDLE;
                end
                default: wstate <= S_W_IDLE;
            endcase
        end
    end

    // ------------------------------------------------------------------
    // read channel
    // ------------------------------------------------------------------
    localparam S_R_IDLE = 2'd0;
    localparam S_R_CALC = 2'd1;
    localparam S_R_DATA = 2'd2;

    reg [1:0]    rstate;
    reg [AW-1:0] raddr_r;
    reg [31:0]   rdata_r;

    assign arready     = (rstate == S_R_IDLE);
    assign rvalid      = (rstate == S_R_DATA);
    assign rresp       = 2'b00;
    assign rdata       = rdata_r;
    assign act_rd_addr = (raddr_r - 16'h0800) >> 2;

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            rstate  <= S_R_IDLE;
            raddr_r <= {AW{1'b0}};
            rdata_r <= 32'd0;
        end else begin
            case (rstate)
                S_R_IDLE: begin
                    if (arvalid) begin
                        raddr_r <= araddr;
                        rstate  <= S_R_CALC;
                    end
                end
                S_R_CALC: begin
                    if (raddr_r >= 16'h0800 && raddr_r < 16'h20c0 && raddr_r[1:0] == 0)
                        rdata_r <= act_rd_data;
                    else case (raddr_r[15:8])
                        8'h00: case (raddr_r[7:2])
                                   6'h01: rdata_r <= {30'd0, done_in, busy};
                                   6'h02: rdata_r <= {28'd0, pred};
                                   6'h03: rdata_r <= cycles;
                                   6'h04: rdata_r <= frame_count;
                                   default: rdata_r <= 32'd0;
                               endcase
                        default: rdata_r <= 32'd0;
                    endcase
                    rstate <= S_R_DATA;
                end
                S_R_DATA: begin
                    if (rready) rstate <= S_R_IDLE;
                end
                default: rstate <= S_R_IDLE;
            endcase
        end
    end

endmodule
