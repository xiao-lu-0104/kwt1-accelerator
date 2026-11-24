`timescale 1ns / 1ps
// 12-layer encoder scheduler with per-layer parameter switching.
//
// One physical kwt_encoder_layer is reused for all 12 layers. Before each
// layer the parameter ROM is scanned and pushed into the layer.
//
// Parameter interface: indexed by {cur_layer, ld_sel, ld_addr}.
// PARAM_HANDSHAKE=0 preserves the combinational-ROM regression interface.
// PARAM_HANDSHAKE=1 accepts a parameter only on param_valid && param_ready;
// the selector/address and all parameter destinations hold during a stall.
// ld_addr drives both the ROM address and the layer's parameter address, so
// the address and data always agree (no one-cycle skew).
//
//   ld_sel 0..3 : Q/K/V/O weights    (4096 nibbles each)
//   ld_sel 4..5 : FFN1/FFN2 weights  (16384 nibbles each)
//   ld_sel 6    : Q/K/V multipliers  (192 words, addr[7:6] selects Q/K/V)
//   ld_sel 7    : O bias + multiplier     (64 words)
//   ld_sel 8    : FFN1 bias + multiplier  (256 words)
//   ld_sel 9    : FFN2 bias + multiplier  (64 words)
//   ld_sel 10..11: LN1 / LN2 gamma+beta   (64 entries each)
//   ld_sel 12   : layer constants         (6 words)
module kwt_encoder_12 #(
    parameter TOK = 99,
    parameter D   = 64,
    parameter FF  = 256,
    parameter NLAYER = 12,
    parameter COMPACT = 1,
    parameter KV_SHARED = 1,
    parameter SOFTMAX_LANES = 4,
    parameter PARAM_HANDSHAKE = 0
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    input  wire               x_we,
    input  wire [12:0]        x_addr,
    input  wire [7:0]         x_data,

    // parameter ROM interface
    output reg  [3:0]         cur_layer,
    output reg  [3:0]         ld_sel,
    output reg  [13:0]        ld_addr,
    input  wire [3:0]         rom_wgt,
    input  wire [63:0]        rom_wgt16,
    input  wire signed [31:0] rom_bias,
    input  wire signed [31:0] rom_m,
    input  wire signed [15:0] rom_ln_gamma,
    input  wire signed [15:0] rom_ln_beta,

    output wire               out_we,
    output wire [12:0]        out_addr,
    output wire [7:0]         out_data,

    output reg                done,
    output reg  [31:0]        cycle_count,
    input  wire              param_valid,
    output wire              param_ready
);

    localparam TACT = TOK*D;
    localparam NW4  = D*D;
    localparam NWF  = D*FF;
    localparam NLR  = NLAYER-1;

    localparam S_IDLE = 4'd0;
    localparam S_LW   = 4'd1;
    localparam S_LBQ  = 4'd2;
    localparam S_LBO  = 4'd3;
    localparam S_LBF1 = 4'd4;
    localparam S_LBF2 = 4'd5;
    localparam S_LLN  = 4'd6;
    localparam S_LLC  = 4'd7;
    localparam S_XF   = 4'd8;
    localparam S_RUN  = 4'd9;
    localparam S_NEXT = 4'd10;
    localparam S_DONE = 4'd11;
    localparam S_XR   = 4'd12;

    // This is a LENGTH, not an address: 16384 needs 15 bits. Truncating it
    // to the 14-bit address width wrapped the FFN length to zero and made
    // the 16-bit counter scan each FFN block four times before advancing.
    function [15:0] wlen(input [3:0] s);
        wlen = (s < 4'd4) ? NW4[15:0] : NWF[15:0];
    endfunction

    reg [3:0]  state;
    reg [15:0] cnt;
    reg [3:0]  sel;
    reg [3:0]  layer;

    reg signed [31:0] m_score_r, m_ctx_r;
    reg signed [15:0] ma1_r, mb1_r, ma2_r, mb2_r;

    wire loading = (state == S_LW) || (state == S_LBQ) ||
                   (state == S_LBO) || (state == S_LBF1) ||
                   (state == S_LBF2) || (state == S_LLN) || (state == S_LLC);
    assign param_ready = (PARAM_HANDSHAKE != 0) && rst_n && loading;
    wire load_accept = (PARAM_HANDSHAKE == 0) || param_valid;
    // Gate writes as well as the scanner. Invalid data must never reach the
    // packed SRAM pending pipeline, LN registers or layer constants.
    wire        ld_wgt  = (state == S_LW) && load_accept;
    wire        ld_bp   = ((state == S_LBQ) || (state == S_LBO) ||
                          (state == S_LBF1) || (state == S_LBF2)) && load_accept;
    wire        ld_ln   = (state == S_LLN) && load_accept;
    wire [2:0]  bp_sel_c = (state == S_LBQ)  ? {1'b0, ld_addr[7:6]} :
                           (state == S_LBO)  ? 3'd3 :
                           (state == S_LBF1) ? 3'd4 : 3'd5;
    // m_buf/bias_buf hold 64 or 256 entries: index must wrap per block
    wire [7:0]  bp_addr_c = (state == S_LBF1) ? ld_addr[7:0] : ld_addr[5:0];

    reg         xin_we;
    reg  [12:0] xin_addr;
    wire [7:0]  xin_data;
    reg         enc_start;

    wire        enc_out_we;
    wire [12:0] enc_out_addr;
    wire [7:0]  enc_out_data;
    wire        enc_done;
    reg         enc_done_d;

    assign out_we   = (layer == NLR) ? enc_out_we : 1'b0;
    assign out_addr = enc_out_addr;
    assign out_data = enc_out_data;

    generate if (COMPACT) begin: g_compact
    kwt_encoder_layer_compact #(.TOK(TOK), .D(D), .FF(FF), .KV_SHARED(KV_SHARED),
        .SOFTMAX_LANES(SOFTMAX_LANES)) u_enc (
        .clk(clk), .rst_n(rst_n), .start(enc_start),
        .x_we(xin_we), .x_addr(xin_addr), .x_data(xin_data),
        .p_wgt_we(1'b0), .p_wgt_sel(ld_sel[2:0]),
        .p_wgt_addr(ld_addr), .p_wgt_data(rom_wgt),
        .p_wgt_we16(ld_wgt), .p_wgt_data16(rom_wgt16),
        .p_bp_we(ld_bp), .p_bp_sel(bp_sel_c),
        .p_bp_addr(bp_addr_c),
        .p_bp_bias(rom_bias), .p_bp_m(rom_m),
        .p_ln_we(ld_ln), .p_ln_sel(ld_addr[6]),
        .p_ln_addr(ld_addr[5:0]),
        .p_ln_gamma(rom_ln_gamma), .p_ln_beta(rom_ln_beta), .p_ln_eps(32'd0),
        .m_score(m_score_r), .m_ctx(m_ctx_r),
        .ma1(ma1_r), .mb1(mb1_r), .ma2(ma2_r), .mb2(mb2_r),
        .out_we(enc_out_we), .out_addr(enc_out_addr), .out_data(enc_out_data),
        .done(enc_done), .cycle_count()
    );
    end else begin: g_legacy
    kwt_encoder_layer #(.TOK(TOK), .D(D), .FF(FF)) u_enc (
        .clk(clk), .rst_n(rst_n), .start(enc_start),
        .x_we(xin_we), .x_addr(xin_addr), .x_data(xin_data),
        .p_wgt_we(1'b0), .p_wgt_sel(ld_sel[2:0]),
        .p_wgt_addr(ld_addr), .p_wgt_data(rom_wgt),
        .p_wgt_we16(ld_wgt), .p_wgt_data16(rom_wgt16),
        .p_bp_we(ld_bp), .p_bp_sel(bp_sel_c), .p_bp_addr(bp_addr_c),
        .p_bp_bias(rom_bias), .p_bp_m(rom_m),
        .p_ln_we(ld_ln), .p_ln_sel(ld_addr[6]), .p_ln_addr(ld_addr[5:0]),
        .p_ln_gamma(rom_ln_gamma), .p_ln_beta(rom_ln_beta), .p_ln_eps(32'd0),
        .m_score(m_score_r), .m_ctx(m_ctx_r),
        .ma1(ma1_r), .mb1(mb1_r), .ma2(ma2_r), .mb2(mb2_r),
        .out_we(enc_out_we), .out_addr(enc_out_addr), .out_data(enc_out_data),
        .done(enc_done), .cycle_count());
    end endgenerate

    // Layer boundary: one packed 16x4096 SRAM, rather than 50,688 FFs.
    wire xh_we=x_we||(enc_out_we&&layer!=NLR);
    wire [12:0] xh_addr=x_we?x_addr:enc_out_addr;
    wire [7:0] xh_data=x_we?x_data:enc_out_data;
    wire [15:0] xh_wdata=xh_addr[0]?{xh_data,8'd0}:{8'd0,xh_data};
    wire [3:0] xh_mask=xh_addr[0]?4'b1100:4'b0011;
    wire [15:0] xh_q;
    wire [15:0] xh_next=cnt+16'd1;
    wire [11:0] xh_ra=(state==S_XF)?xh_next[12:1]:12'd0;
    kwt_packed_sram #(.DW(16),.DEPTH(4096)) u_xhold (
        .clk(clk),.rst_n(rst_n),.wr(xh_we),.wa(xh_addr[12:1]),
        .wd(xh_wdata),.mask(xh_mask),.ra(xh_ra),.rd(xh_q));
    assign xin_data=xin_addr[0]?xh_q[15:8]:xh_q[7:0];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) enc_done_d <= 1'b0;
        else        enc_done_d <= enc_done;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            cnt         <= 16'd0;
            sel         <= 4'd0;
            layer       <= 4'd0;
            cur_layer   <= 4'd0;
            ld_sel      <= 4'd0;
            ld_addr     <= 14'd0;
            xin_we      <= 1'b0;
            xin_addr    <= 13'd0;
            enc_start   <= 1'b0;
            m_score_r   <= 32'sd0;
            m_ctx_r     <= 32'sd0;
            ma1_r       <= 16'sd0;
            mb1_r       <= 16'sd0;
            ma2_r       <= 16'sd0;
            mb2_r       <= 16'sd0;
            done        <= 1'b0;
            cycle_count <= 32'd0;
        end else begin
            cycle_count <= cycle_count + 32'd1;
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    if (start) begin
                        cycle_count <= 32'd0;
                        layer       <= 4'd0;
                        cur_layer   <= 4'd0;
                        sel         <= 4'd0;
                        cnt         <= 16'd0;
                        ld_sel      <= 4'd0;
                        ld_addr     <= 14'd0;
                        state       <= S_LW;
                    end
                end

                // -------- weights: sel 0..5 (16 nibbles per cycle) --------
                S_LW: if (load_accept) begin
                    if (cnt >= wlen(sel) - 16'd16) begin
                        cnt     <= 16'd0;
                        ld_addr <= 14'd0;
                        if (sel == 4'd5) begin
                            ld_sel <= 4'd6;
                            state  <= S_LBQ;
                        end else begin
                            sel    <= sel + 4'd1;
                            ld_sel <= sel + 4'd1;
                        end
                    end else begin
                        cnt     <= cnt + 16'd16;
                        ld_addr <= ld_addr + 14'd16;
                    end
                end

                // -------- Q/K/V multipliers  (3 x 64, addr[7:6] selects) --------
                S_LBQ: if (load_accept) begin
                    if (cnt == 16'd191) begin
                        cnt     <= 16'd0;
                        ld_addr <= 14'd0;
                        ld_sel  <= 4'd7;
                        state   <= S_LBO;
                    end else begin
                        cnt     <= cnt + 16'd1;
                        ld_addr <= ld_addr + 14'd1;
                    end
                end

                // -------- O bias/m  (64) --------
                S_LBO: if (load_accept) begin
                    if (cnt == 16'd63) begin
                        cnt     <= 16'd0;
                        ld_addr <= 14'd0;
                        ld_sel  <= 4'd8;
                        state   <= S_LBF1;
                    end else begin
                        cnt     <= cnt + 16'd1;
                        ld_addr <= ld_addr + 14'd1;
                    end
                end

                // -------- FFN1 bias/m  (256) --------
                S_LBF1: if (load_accept) begin
                    if (cnt == 16'd255) begin
                        cnt     <= 16'd0;
                        ld_addr <= 14'd0;
                        ld_sel  <= 4'd9;
                        state   <= S_LBF2;
                    end else begin
                        cnt     <= cnt + 16'd1;
                        ld_addr <= ld_addr + 14'd1;
                    end
                end

                // -------- FFN2 bias/m  (64) --------
                S_LBF2: if (load_accept) begin
                    if (cnt == 16'd63) begin
                        cnt     <= 16'd0;
                        ld_addr <= 14'd0;
                        ld_sel  <= 4'd10;
                        state   <= S_LLN;
                    end else begin
                        cnt     <= cnt + 16'd1;
                        ld_addr <= ld_addr + 14'd1;
                    end
                end

                // -------- LN1 (0..63) then LN2 (64..127) --------
                S_LLN: if (load_accept) begin
                    if (cnt == 16'd127) begin
                        cnt     <= 16'd0;
                        ld_addr <= 14'd0;
                        ld_sel  <= 4'd12;
                        state   <= S_LLC;
                    end else begin
                        cnt     <= cnt + 16'd1;
                        ld_addr <= ld_addr + 14'd1;
                    end
                end

                // -------- layer constants (6) --------
                S_LLC: if (load_accept) begin
                    case (cnt)
                        16'd0: m_score_r <= rom_m;
                        16'd1: m_ctx_r   <= rom_m;
                        16'd2: ma1_r     <= rom_m[15:0];
                        16'd3: mb1_r     <= rom_m[15:0];
                        16'd4: ma2_r     <= rom_m[15:0];
                        16'd5: mb2_r     <= rom_m[15:0];
                        default: ;
                    endcase
                    if (cnt == 16'd5) begin
                        cnt      <= 16'd0;
                        xin_we   <= 1'b0;
                        xin_addr <= 13'd0;
                        state    <= S_XR;
                    end else begin
                        cnt     <= cnt + 16'd1;
                        ld_addr <= ld_addr + 14'd1;
                    end
                end

                // Prime the synchronous boundary SRAM before the first byte.
                S_XR: begin
                    xin_we <= 1'b1;
                    state <= S_XF;
                end
                // -------- feed activation --------
                S_XF: begin
                    if (cnt == TACT-1) begin
                        xin_we    <= 1'b0;
                        cnt       <= 16'd0;
                        enc_start <= 1'b1;
                        state     <= S_RUN;
                    end else begin
                        cnt      <= cnt + 16'd1;
                        xin_addr <= cnt[12:0] + 13'd1;
                    end
                end

                S_RUN: begin
                    enc_start <= 1'b0;
                    if (enc_done && !enc_done_d) state <= S_NEXT;
                end

                S_NEXT: begin
                    if (layer == NLR) begin
                        done  <= 1'b1;
                        state <= S_DONE;
                    end else begin
                        layer     <= layer + 4'd1;
                        cur_layer <= layer + 4'd1;
                        sel       <= 4'd0;
                        cnt       <= 16'd0;
                        ld_sel    <= 4'd0;
                        ld_addr   <= 14'd0;
                        state     <= S_LW;
                    end
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
