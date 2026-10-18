`timescale 1ns / 1ps
// KWT-1 top level: MFCC -> patch projection -> class token + positional
// embedding -> 12 encoder layers -> classifier head -> argmax.
//
// Activation stream inside the chip is 99 tokens x 64 channels of int8 at
// scale s_x (input) / s_out (after the encoder).
module kwt_top #(
    parameter TOK = 99,
    parameter D   = 64,
    parameter FF  = 256,
    parameter NCLS = 12,
    parameter NLAYER = 12
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    // MFCC input: 98 x 40 int8 (zero padded to 64 lanes internally)
    input  wire               mf_we,
    input  wire [12:0]        mf_addr,      // token*64 + channel, 0..6271
    input  wire [7:0]         mf_data,

    // patch projection parameters
    input  wire               pp_wgt_we,
    input  wire [11:0]        pp_wgt_addr,  // 64*64 nibbles
    input  wire [3:0]         pp_wgt_data,
    input  wire               pp_bp_we,
    input  wire [5:0]         pp_bp_addr,
    input  wire signed [31:0] pp_bp_bias,
    input  wire signed [31:0] pp_bp_m,

    // class token and positional embedding, already quantised to s_x
    input  wire               cp_we,
    input  wire [12:0]        cp_addr,      // 0..6335, row 0 is the class token
    input  wire [7:0]         cp_data,

    // encoder parameter ROM (see kwt_encoder_12)
    output wire [3:0]         cur_layer,
    output wire [3:0]         ld_sel,
    output wire [13:0]        ld_addr,
    input  wire [3:0]         rom_wgt,
    input  wire [63:0]        rom_wgt16,
    input  wire signed [31:0] rom_bias,
    input  wire signed [31:0] rom_m,
    input  wire signed [15:0] rom_ln_gamma,
    input  wire signed [15:0] rom_ln_beta,

    // classifier head parameters
    input  wire               hd_wgt_we,
    input  wire [9:0]         hd_wgt_addr,  // 16*64 nibbles
    input  wire [3:0]         hd_wgt_data,
    input  wire               hd_bp_we,
    input  wire [3:0]         hd_bp_addr,
    input  wire signed [31:0] hd_bp_bias,
    input  wire signed [31:0] hd_bp_m,

    output reg  [3:0]         pred_class,
    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam TP   = 98;            // patch tokens
    localparam TACT = TOK*D;         // 6336
    localparam PACT = TP*D;          // 6272

    localparam S_IDLE = 4'd0;
    localparam S_PP   = 4'd1;        // patch projection GEMM
    localparam S_PPW  = 4'd2;
    localparam S_CLS  = 4'd3;        // class token + positional add
    localparam S_ENC  = 4'd4;
    localparam S_HD   = 4'd5;
    localparam S_HDW  = 4'd6;
    localparam S_ARG  = 4'd7;
    localparam S_ARG2 = 4'd8;
    localparam S_DONE = 4'd9;

    reg [3:0]  state;
    reg [15:0] cnt;

    // ---------------- patch projection ----------------
    reg         pp_start;
    reg         pp_act_we;
    reg  [12:0] pp_act_addr;
    reg  [7:0]  pp_act_data;
    wire        pp_done;
    wire        pp_out_we;
    wire [10:0] pp_out_addr;         // token*(64/4) + group, 0..1567
    wire [31:0] pp_out_data;

    reg [7:0]  act_buf [0:PACT-1];
    reg [7:0]  pp_buf  [0:TACT-1];
    reg [7:0]  cp_buf  [0:TACT-1];
    reg [7:0]  out_buf [0:TACT-1];
    reg [7:0]  hd_buf  [0:D-1];

    // encoder activation write port
    reg         enc_x_we;
    reg  [12:0] enc_x_addr;
    reg  [7:0]  enc_x_data;

    function signed [7:0] sat8(input signed [8:0] v);
        sat8 = (v > 9'sd127) ? 8'sd127 : (v < -9'sd127) ? -8'sd127 : v[7:0];
    endfunction

    kwt_gemm_engine #(
        .IN_DIM(D), .OUT_DIM(D), .TOKENS(TP), .WB(4), .OUT_BITS(8),
        .AW_ACT(13), .AW_WGT(12), .AW_BP(6), .AW_OUT(11)
    ) u_pp (
        .clk(clk), .rst_n(rst_n), .start(pp_start),
        .act_we(pp_act_we), .act_addr(pp_act_addr), .act_data(pp_act_data),
        .act_we4(1'b0), .act_data32(32'd0),
        .wgt_we(pp_wgt_we), .wgt_addr(pp_wgt_addr), .wgt_data(pp_wgt_data),
        .wgt_we16(1'b0), .wgt_data16(64'd0), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(pp_bp_we), .bp_addr(pp_bp_addr),
        .bp_bias(pp_bp_bias), .bp_m(pp_bp_m),
        .out_we(pp_out_we), .out_addr(pp_out_addr), .out_data(pp_out_data),
        .done(pp_done), .cycle_count()
    );

    // ---------------- encoder ----------------
    reg         enc_start;
    wire        enc_out_we;
    wire [12:0] enc_out_addr;
    wire [7:0]  enc_out_data;
    wire        enc_done;

    kwt_encoder_12 #(.TOK(TOK), .D(D), .FF(FF), .NLAYER(NLAYER)) u_enc (
        .clk(clk), .rst_n(rst_n), .start(enc_start),
        .x_we(enc_x_we), .x_addr(enc_x_addr), .x_data(enc_x_data),
        .cur_layer(cur_layer), .ld_sel(ld_sel), .ld_addr(ld_addr),
        .rom_wgt(rom_wgt), .rom_wgt16(rom_wgt16), .rom_bias(rom_bias), .rom_m(rom_m),
        .rom_ln_gamma(rom_ln_gamma), .rom_ln_beta(rom_ln_beta),
        .out_we(enc_out_we), .out_addr(enc_out_addr), .out_data(enc_out_data),
        .done(enc_done), .cycle_count()
    );

    // xhold inside kwt_encoder_12 is loaded through the public x_we port, so
    // feed the encoder's activation from here by re-driving that port.
    // (declared below as the shared activation write port)

    // ---------------- classifier head ----------------
    reg         hd_start;
    reg         hd_act_we;
    reg  [5:0]  hd_act_addr;
    reg  [7:0]  hd_act_data;
    wire        hd_done;
    wire        hd_out_we;
    wire [1:0]  hd_out_addr;
    wire [31:0] hd_out_data;

    kwt_gemm_engine #(
        .IN_DIM(D), .OUT_DIM(16), .TOKENS(1), .WB(4), .OUT_BITS(8),
        .AW_ACT(6), .AW_WGT(10), .AW_BP(4), .AW_OUT(2)
    ) u_head (
        .clk(clk), .rst_n(rst_n), .start(hd_start),
        .act_we(hd_act_we), .act_addr(hd_act_addr), .act_data(hd_act_data),
        .act_we4(1'b0), .act_data32(32'd0),
        .wgt_we(hd_wgt_we), .wgt_addr(hd_wgt_addr), .wgt_data(hd_wgt_data),
        .wgt_we16(1'b0), .wgt_data16(64'd0), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(hd_bp_we), .bp_addr(hd_bp_addr),
        .bp_bias(hd_bp_bias), .bp_m(hd_bp_m),
        .out_we(hd_out_we), .out_addr(hd_out_addr), .out_data(hd_out_data),
        .done(hd_done), .cycle_count()
    );

    // ---------------- argmax over the first 12 logits ----------------
    reg signed [7:0] lg [0:15];
    reg [3:0] best_idx;
    reg signed [7:0] best_val;

    integer m;
    always @(*) begin
        best_idx = 4'd0;
        best_val = lg[0];
        for (m = 1; m < NCLS; m = m + 1) begin
            if (lg[m] > best_val) begin
                best_val = lg[m];
                best_idx = m[3:0];
            end
        end
    end

    // ---------------- sequencing ----------------
    always @(posedge clk) begin
        if (mf_we)    act_buf[mf_addr < PACT ? mf_addr : 12'd0] <= mf_data;
        if (cp_we)    cp_buf[cp_addr] <= cp_data;
        if (pp_out_we && pp_out_addr < (PACT/4)) begin
            pp_buf[{pp_out_addr, 2'b00}] <= pp_out_data[7:0];
            pp_buf[{pp_out_addr, 2'b01}] <= pp_out_data[15:8];
            pp_buf[{pp_out_addr, 2'b10}] <= pp_out_data[23:16];
            pp_buf[{pp_out_addr, 2'b11}] <= pp_out_data[31:24];
        end
        if (hd_out_we) begin
            hd_buf[{hd_out_addr, 2'b00}] <= hd_out_data[7:0];
            hd_buf[{hd_out_addr, 2'b01}] <= hd_out_data[15:8];
            hd_buf[{hd_out_addr, 2'b10}] <= hd_out_data[23:16];
            hd_buf[{hd_out_addr, 2'b11}] <= hd_out_data[31:24];
        end
        if (enc_out_we) out_buf[enc_out_addr] <= enc_out_data;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            cnt         <= 16'd0;
            pp_start    <= 1'b0;
            pp_act_we   <= 1'b0;
            pp_act_addr <= 13'd0;
            pp_act_data <= 8'd0;
            enc_start   <= 1'b0;
            hd_start    <= 1'b0;
            hd_act_we   <= 1'b0;
            hd_act_addr <= 6'd0;
            hd_act_data <= 8'd0;
            enc_x_we    <= 1'b0;
            enc_x_addr  <= 13'd0;
            enc_x_data  <= 8'd0;
            pred_class  <= 4'd0;
            done        <= 1'b0;
            cycle_count <= 32'd0;
        end else begin
            cycle_count <= cycle_count + 32'd1;
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    if (start) begin
                        cycle_count <= 32'd0;
                        cnt         <= 16'd0;
                        pp_act_we   <= 1'b1;
                        pp_act_addr <= 13'd0;
                        pp_act_data <= act_buf[0];
                        state       <= S_PP;
                    end
                end

                // stream the 98x64 (zero padded) activation in
                S_PP: begin
                    if (cnt == PACT-1) begin
                        pp_act_we <= 1'b0;
                        cnt       <= 16'd0;
                        pp_start  <= 1'b1;
                        state     <= S_PPW;
                    end else begin
                        cnt         <= cnt + 16'd1;
                        pp_act_addr <= cnt[12:0] + 13'd1;
                        pp_act_data <= act_buf[cnt[12:0] + 13'd1];
                    end
                end

                S_PPW: begin
                    pp_start <= 1'b0;
                    if (pp_done) begin
                        cnt        <= 16'd0;
                        enc_x_we   <= 1'b1;
                        enc_x_addr <= 13'd0;
                        enc_x_data <= cp_buf[0];
                        state      <= S_CLS;
                    end
                end

                // token 0 = class token + pos_emb[0]; others = patch + pos_emb.
                // Address and data are advanced one cycle ahead so the last
                // element (index TACT-1) is written before we drop enc_x_we.
                S_CLS: begin
                    enc_x_addr <= cnt[12:0] + 13'd1;
                    enc_x_data <= (cnt[12:0] + 13'd1 < D)
                                  ? cp_buf[cnt[12:0] + 13'd1]
                                  : sat8($signed({pp_buf[cnt[12:0] + 13'd1 - 13'd64]}) +
                                         $signed(cp_buf[cnt[12:0] + 13'd1]));
                    cnt <= cnt + 16'd1;
                    if (cnt == TACT-1) begin
                        enc_x_we  <= 1'b0;
                        cnt       <= 16'd0;
                        enc_start <= 1'b1;
                        state     <= S_ENC;
                    end
                end

                S_ENC: begin
                    enc_start <= 1'b0;
                    if (enc_done) begin
                        cnt         <= 16'd0;
                        hd_act_we   <= 1'b1;
                        hd_act_addr <= 6'd0;
                        hd_act_data <= out_buf[0];
                        state       <= S_HD;
                    end
                end

                // stream the class token into the head
                S_HD: begin
                    hd_act_addr <= cnt[5:0] + 6'd1;
                    hd_act_data <= out_buf[cnt[5:0] + 6'd1];
                    cnt         <= cnt + 16'd1;
                    if (cnt == D-1) begin
                        hd_act_we <= 1'b0;
                        cnt       <= 16'd0;
                        hd_start  <= 1'b1;
                        state     <= S_HDW;
                    end
                end

                S_HDW: begin
                    hd_start <= 1'b0;
                    if (hd_done) begin
                        cnt   <= 16'd0;
                        state <= S_ARG;
                    end
                end

                S_ARG: begin
                    lg[0]  <= $signed(hd_buf[0]);
                    lg[1]  <= $signed(hd_buf[1]);
                    lg[2]  <= $signed(hd_buf[2]);
                    lg[3]  <= $signed(hd_buf[3]);
                    lg[4]  <= $signed(hd_buf[4]);
                    lg[5]  <= $signed(hd_buf[5]);
                    lg[6]  <= $signed(hd_buf[6]);
                    lg[7]  <= $signed(hd_buf[7]);
                    lg[8]  <= $signed(hd_buf[8]);
                    lg[9]  <= $signed(hd_buf[9]);
                    lg[10] <= $signed(hd_buf[10]);
                    lg[11] <= $signed(hd_buf[11]);
                    state  <= S_ARG2;
                end

                S_ARG2: begin
                    pred_class <= best_idx;
                    done       <= 1'b1;
                    state      <= S_DONE;
                end

                S_DONE: begin
                    if (!start) begin
                        done  <= 1'b0;
                        state <= S_IDLE;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
