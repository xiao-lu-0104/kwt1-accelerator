`timescale 1ns / 1ps
// One PostNorm transformer encoder layer.
//
//   x -> attention -> o
//   r1 = align(x, o) -> LN1 -> x1
//   h  = F1 * x1 + b1 -> GELU (s_hin -> s_h)
//   f  = F2 * h  + b2
//   r2 = align(x1, f) -> LN2 -> out
//
// Parameter ports (loaded before start):
//   p_wgt_sel / p_bp_sel: 0=Q 1=K 2=V 3=O 4=FFN1 5=FFN2
//   p_ln_sel: 0=LN1 1=LN2
module kwt_encoder_layer #(
    parameter TOK = 99,
    parameter D   = 64,
    parameter FF  = 256
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    input  wire               x_we,
    input  wire [12:0]        x_addr,
    input  wire [7:0]         x_data,

    input  wire               p_wgt_we,
    input  wire [2:0]         p_wgt_sel,
    input  wire [13:0]        p_wgt_addr,
    input  wire [3:0]         p_wgt_data,
    input  wire               p_wgt_we16,
    input  wire [63:0]        p_wgt_data16,

    input  wire               p_bp_we,
    input  wire [2:0]         p_bp_sel,
    input  wire [7:0]         p_bp_addr,
    input  wire signed [31:0] p_bp_bias,
    input  wire signed [31:0] p_bp_m,

    input  wire               p_ln_we,
    input  wire               p_ln_sel,
    input  wire [5:0]         p_ln_addr,
    input  wire signed [15:0] p_ln_gamma,
    input  wire signed [15:0] p_ln_beta,
    input  wire [31:0]        p_ln_eps,

    input  wire signed [31:0] m_score,
    input  wire signed [31:0] m_ctx,
    input  wire signed [15:0] ma1,
    input  wire signed [15:0] mb1,
    input  wire signed [15:0] ma2,
    input  wire signed [15:0] mb2,

    output reg                out_we,
    output reg  [12:0]        out_addr,
    output reg  [7:0]         out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam TACT  = TOK*D;        // 6336
    localparam HACT  = TOK*FF;       // 25344
    localparam NWD   = TOK*(D/4);    // 1584
    localparam NWD_H = TOK*(FF/4);   // 6336

    localparam S_IDLE   = 5'd0;
    localparam S_ATTN   = 5'd1;
    localparam S_ALIGN1 = 5'd2;
    localparam S_LN1P   = 5'd3;
    localparam S_LN1I   = 5'd4;
    localparam S_LN1    = 5'd5;
    localparam S_FFN1I  = 5'd6;
    localparam S_FFN1   = 5'd7;
    localparam S_GELU   = 5'd8;
    localparam S_GELUD  = 5'd9;
    localparam S_FFN2I  = 5'd10;
    localparam S_FFN2   = 5'd11;
    localparam S_ALIGN2 = 5'd12;
    localparam S_LN2P   = 5'd13;
    localparam S_LN2I   = 5'd14;
    localparam S_LN2    = 5'd15;
    localparam S_DONE   = 5'd16;

    // ------------------------------------------------------------------
    // buffers
    // ------------------------------------------------------------------
    reg [7:0]         x_buf  [0:TACT-1];
    reg [7:0]         o_buf  [0:TACT-1];
    reg signed [15:0] r1_buf [0:TACT-1];
    reg [7:0]         x1_buf [0:TACT-1];
    reg [7:0]         h_buf  [0:HACT-1];
    reg [7:0]         f_buf  [0:TACT-1];
    reg signed [15:0] r2_buf [0:TACT-1];

    reg signed [15:0] ln_g [0:1][0:D-1];
    reg signed [15:0] ln_b [0:1][0:D-1];

    // ------------------------------------------------------------------
    // FSM state
    // ------------------------------------------------------------------
    reg [4:0]  state;
    reg [15:0] cnt;
    reg [15:0] hcnt;
    reg [3:0]  wait_cnt;
    reg        start_d;

    // attention
    reg         at_start;
    wire        at_done;
    wire        at_out_we;
    wire [12:0] at_out_addr;
    wire [31:0] at_out_data;

    // align
    reg  signed [15:0] al_y0, al_y1, al_y2, al_y3;

    // layernorm
    reg         ln_start;
    reg         ln_in_we;
    reg  [12:0] ln_in_addr;
    reg  signed [15:0] ln_in_data;
    reg         ln_gp_we;
    reg  [5:0]  ln_gp_addr;
    reg  signed [15:0] ln_gp_gamma, ln_gp_beta;
    reg  [31:0] ln_eps;
    wire        ln_out_we;
    wire [12:0] ln_out_addr;
    wire signed [7:0] ln_out_data;
    wire        ln_done;

    // FFN1
    reg         f1_start;
    wire        f1_we   = 1'b0;
    wire [12:0] f1_addr = cnt[12:0];
    wire [7:0]  f1_data = 8'd0;
    wire        f1_we4  = (state == S_FFN1I);
    wire [31:0] f1_data32 = {x1_buf[cnt[12:0] + 13'd3], x1_buf[cnt[12:0] + 13'd2],
                             x1_buf[cnt[12:0] + 13'd1], x1_buf[cnt[12:0]]};
    wire        f1_done;
    wire        f1_out_we;
    wire [12:0] f1_out_addr;
    wire [31:0] f1_out_data;

    // FFN2
    reg         f2_start;
    wire        f2_we   = 1'b0;
    wire [14:0] f2_addr = cnt[14:0];
    wire [7:0]  f2_data = 8'd0;
    wire        f2_we4  = (state == S_FFN2I);
    wire [31:0] f2_data32 = {h_buf[cnt[14:0] + 15'd3], h_buf[cnt[14:0] + 15'd2],
                             h_buf[cnt[14:0] + 15'd1], h_buf[cnt[14:0]]};
    wire        f2_done;
    wire        f2_out_we;
    wire [10:0] f2_out_addr;
    wire [31:0] f2_out_data;

    // GELU (4 lanes, 25344/4 = 6336 passes)
    reg         gelu_valid;
    reg  signed [7:0] gelu_x0, gelu_x1, gelu_x2, gelu_x3;
    wire signed [7:0] gelu_y0, gelu_y1, gelu_y2, gelu_y3;
    wire        gelu_valid_out;
    reg  [14:0] gelu_wr;

    wire sel_attn = (p_wgt_sel < 3'd4);
    wire sel_f1   = (p_wgt_sel == 3'd4);
    wire sel_f2   = (p_wgt_sel == 3'd5);
    wire bsel_attn = (p_bp_sel < 3'd4);
    wire bsel_f1   = (p_bp_sel == 3'd4);
    wire bsel_f2   = (p_bp_sel == 3'd5);

    // ------------------------------------------------------------------
    // sub-modules
    // ------------------------------------------------------------------
    kwt_attention u_attn (
        .clk(clk), .rst_n(rst_n), .start(at_start),
        .x_we(x_we), .x_addr(x_addr), .x_data(x_data),
        .p_wgt_we(p_wgt_we && sel_attn), .p_wgt_sel(p_wgt_sel[1:0]),
        .p_wgt_addr(p_wgt_addr), .p_wgt_data(p_wgt_data),
        .p_wgt_we16(p_wgt_we16 && sel_attn), .p_wgt_data16(p_wgt_data16),
        .p_bp_we(p_bp_we && bsel_attn), .p_bp_sel(p_bp_sel[1:0]),
        .p_bp_addr(p_bp_addr), .p_bp_bias(p_bp_bias), .p_bp_m(p_bp_m),
        .m_score(m_score), .m_ctx(m_ctx),
        .out_we(at_out_we), .out_addr(at_out_addr), .out_data(at_out_data),
        .done(at_done), .cycle_count()
    );

    kwt_layernorm #(.N(D), .ROWS(TOK), .AW(13)) u_ln (
        .clk(clk), .rst_n(rst_n), .start(ln_start),
        .in_we(ln_in_we), .in_addr(ln_in_addr), .in_data(ln_in_data),
        .gp_we(ln_gp_we), .gp_addr(ln_gp_addr),
        .gp_gamma(ln_gp_gamma), .gp_beta(ln_gp_beta), .eps_q(ln_eps),
        .out_we(ln_out_we), .out_addr(ln_out_addr), .out_data(ln_out_data),
        .done(ln_done), .cycle_count()
    );

    kwt_gemm_engine #(
        .IN_DIM(D), .OUT_DIM(FF), .TOKENS(TOK), .WB(4), .OUT_BITS(8),
        .AW_ACT(13), .AW_WGT(14), .AW_BP(8), .AW_OUT(13)
    ) u_ffn1 (
        .clk(clk), .rst_n(rst_n), .start(f1_start),
        .act_we(f1_we), .act_addr(f1_addr), .act_data(f1_data),
        .act_we4(f1_we4), .act_data32(f1_data32),
        .wgt_we(p_wgt_we && sel_f1), .wgt_addr(p_wgt_addr), .wgt_data(p_wgt_data),
        .wgt_we16(p_wgt_we16 && sel_f1), .wgt_data16(p_wgt_data16), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(p_bp_we && bsel_f1), .bp_addr(p_bp_addr),
        .bp_bias(p_bp_bias), .bp_m(p_bp_m),
        .out_we(f1_out_we), .out_addr(f1_out_addr), .out_data(f1_out_data),
        .done(f1_done), .cycle_count()
    );

    kwt_gemm_engine #(
        .IN_DIM(FF), .OUT_DIM(D), .TOKENS(TOK), .WB(4), .OUT_BITS(8),
        .AW_ACT(15), .AW_WGT(14), .AW_BP(8), .AW_OUT(11)
    ) u_ffn2 (
        .clk(clk), .rst_n(rst_n), .start(f2_start),
        .act_we(f2_we), .act_addr(f2_addr), .act_data(f2_data),
        .act_we4(f2_we4), .act_data32(f2_data32),
        .wgt_we(p_wgt_we && sel_f2), .wgt_addr(p_wgt_addr), .wgt_data(p_wgt_data),
        .wgt_we16(p_wgt_we16 && sel_f2), .wgt_data16(p_wgt_data16), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(p_bp_we && bsel_f2), .bp_addr(p_bp_addr),
        .bp_bias(p_bp_bias), .bp_m(p_bp_m),
        .out_we(f2_out_we), .out_addr(f2_out_addr), .out_data(f2_out_data),
        .done(f2_done), .cycle_count()
    );

    kwt_gelu u_gelu0 (
        .clk(clk), .rst_n(rst_n), .valid_in(gelu_valid),
        .x_in(gelu_x0), .y_out(gelu_y0), .valid_out(gelu_valid_out)
    );
    kwt_gelu u_gelu1 (
        .clk(clk), .rst_n(rst_n), .valid_in(gelu_valid),
        .x_in(gelu_x1), .y_out(gelu_y1), .valid_out()
    );
    kwt_gelu u_gelu2 (
        .clk(clk), .rst_n(rst_n), .valid_in(gelu_valid),
        .x_in(gelu_x2), .y_out(gelu_y2), .valid_out()
    );
    kwt_gelu u_gelu3 (
        .clk(clk), .rst_n(rst_n), .valid_in(gelu_valid),
        .x_in(gelu_x3), .y_out(gelu_y3), .valid_out()
    );

    // align operand selection is state-driven (4 lanes per cycle)
    wire signed [15:0] al_ma = (state == S_ALIGN1) ? ma1 : ma2;
    wire signed [15:0] al_mb = (state == S_ALIGN1) ? mb1 : mb2;

    kwt_align_add u_al0 (
        .a((state == S_ALIGN1) ? $signed(x_buf [cnt[12:0]]) : $signed(x1_buf[cnt[12:0]])),
        .b((state == S_ALIGN1) ? $signed(o_buf [cnt[12:0]]) : $signed(f_buf [cnt[12:0]])),
        .ma(al_ma), .mb(al_mb), .y(al_y0));
    kwt_align_add u_al1 (
        .a((state == S_ALIGN1) ? $signed(x_buf [cnt[12:0] + 13'd1]) : $signed(x1_buf[cnt[12:0] + 13'd1])),
        .b((state == S_ALIGN1) ? $signed(o_buf [cnt[12:0] + 13'd1]) : $signed(f_buf [cnt[12:0] + 13'd1])),
        .ma(al_ma), .mb(al_mb), .y(al_y1));
    kwt_align_add u_al2 (
        .a((state == S_ALIGN1) ? $signed(x_buf [cnt[12:0] + 13'd2]) : $signed(x1_buf[cnt[12:0] + 13'd2])),
        .b((state == S_ALIGN1) ? $signed(o_buf [cnt[12:0] + 13'd2]) : $signed(f_buf [cnt[12:0] + 13'd2])),
        .ma(al_ma), .mb(al_mb), .y(al_y2));
    kwt_align_add u_al3 (
        .a((state == S_ALIGN1) ? $signed(x_buf [cnt[12:0] + 13'd3]) : $signed(x1_buf[cnt[12:0] + 13'd3])),
        .b((state == S_ALIGN1) ? $signed(o_buf [cnt[12:0] + 13'd3]) : $signed(f_buf [cnt[12:0] + 13'd3])),
        .ma(al_ma), .mb(al_mb), .y(al_y3));

    // ------------------------------------------------------------------
    // buffer write-back
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (x_we) x_buf[x_addr] <= x_data;
        if (p_ln_we) begin
            ln_g[p_ln_sel][p_ln_addr] <= p_ln_gamma;
            ln_b[p_ln_sel][p_ln_addr] <= p_ln_beta;
        end
        // attention result: 4 packed int8 per word
        if (at_out_we) begin
            o_buf[{at_out_addr, 2'b00}] <= at_out_data[7:0];
            o_buf[{at_out_addr, 2'b01}] <= at_out_data[15:8];
            o_buf[{at_out_addr, 2'b10}] <= at_out_data[23:16];
            o_buf[{at_out_addr, 2'b11}] <= at_out_data[31:24];
        end
        // align result (4 lanes per cycle)
        if (state == S_ALIGN1) begin
            r1_buf[cnt[12:0]]         <= al_y0;
            r1_buf[cnt[12:0] + 13'd1] <= al_y1;
            r1_buf[cnt[12:0] + 13'd2] <= al_y2;
            r1_buf[cnt[12:0] + 13'd3] <= al_y3;
        end
        if (state == S_ALIGN2) begin
            r2_buf[cnt[12:0]]         <= al_y0;
            r2_buf[cnt[12:0] + 13'd1] <= al_y1;
            r2_buf[cnt[12:0] + 13'd2] <= al_y2;
            r2_buf[cnt[12:0] + 13'd3] <= al_y3;
        end
        // LN1 output feeds the FFN; LN2 output streams straight out
        if (ln_out_we && state == S_LN1) x1_buf[ln_out_addr] <= ln_out_data;
        // FFN1 output: 4 packed int8 per word, 64 groups per token
        if (f1_out_we) begin
            h_buf[{f1_out_addr[12:0], 2'b00}] <= f1_out_data[7:0];
            h_buf[{f1_out_addr[12:0], 2'b01}] <= f1_out_data[15:8];
            h_buf[{f1_out_addr[12:0], 2'b10}] <= f1_out_data[23:16];
            h_buf[{f1_out_addr[12:0], 2'b11}] <= f1_out_data[31:24];
        end
        // GELU, in place (4 lanes per cycle)
        if (gelu_valid_out) begin
            h_buf[gelu_wr]         <= gelu_y0;
            h_buf[gelu_wr + 15'd1] <= gelu_y1;
            h_buf[gelu_wr + 15'd2] <= gelu_y2;
            h_buf[gelu_wr + 15'd3] <= gelu_y3;
            gelu_wr <= gelu_wr + 15'd4;
        end
        // FFN2 output: 4 packed int8 per word, 16 groups per token
        if (f2_out_we) begin
            f_buf[{f2_out_addr, 2'b00}] <= f2_out_data[7:0];
            f_buf[{f2_out_addr, 2'b01}] <= f2_out_data[15:8];
            f_buf[{f2_out_addr, 2'b10}] <= f2_out_data[23:16];
            f_buf[{f2_out_addr, 2'b11}] <= f2_out_data[31:24];
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_we   <= 1'b0;
            out_addr <= 13'd0;
            out_data <= 8'd0;
        end else begin
            out_we <= 1'b0;
            if (ln_out_we && state == S_LN2) begin
                out_we   <= 1'b1;
                out_addr <= ln_out_addr;
                out_data <= ln_out_data;
            end
        end
    end

    // ------------------------------------------------------------------
    // main FSM
    // ------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            cnt         <= 16'd0;
            hcnt        <= 16'd0;
            wait_cnt    <= 4'd0;
            at_start    <= 1'b0;
            ln_start    <= 1'b0;
            ln_in_we    <= 1'b0;
            ln_in_addr  <= 13'd0;
            ln_in_data  <= 16'sd0;
            ln_gp_we    <= 1'b0;
            ln_gp_addr  <= 6'd0;
            ln_gp_gamma <= 16'sd0;
            ln_gp_beta  <= 16'sd0;
            ln_eps      <= 32'd0;
            f1_start    <= 1'b0;
            f2_start    <= 1'b0;
            gelu_valid  <= 1'b0;
            gelu_x0     <= 8'sd0;
            gelu_x1     <= 8'sd0;
            gelu_x2     <= 8'sd0;
            gelu_x3     <= 8'sd0;
            gelu_wr     <= 15'd0;
            done        <= 1'b0;
            start_d     <= 1'b0;
            cycle_count <= 32'd0;
        end else begin
            cycle_count <= cycle_count + 32'd1;
            start_d     <= start;
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    cnt  <= 16'd0;
                    if (start) begin
                        cycle_count <= 32'd0;
                        ln_eps      <= p_ln_eps;
                        at_start    <= 1'b1;
                        state       <= S_ATTN;
                    end
                end

                S_ATTN: begin
                    at_start <= 1'b0;
                    if (at_done) begin
                        cnt   <= 16'd0;
                        state <= S_ALIGN1;
                    end
                end

                // al_y is combinational on cnt; write-back captures it
                S_ALIGN1: begin
                    if (cnt >= TACT-4) begin
                        cnt         <= 16'd0;
                        ln_gp_we    <= 1'b1;
                        ln_gp_addr  <= 6'd0;
                        ln_gp_gamma <= ln_g[0][0];
                        ln_gp_beta  <= ln_b[0][0];
                        state       <= S_LN1P;
                    end else begin
                        cnt <= cnt + 16'd4;
                    end
                end

                S_LN1P: begin
                    if (cnt == D-1) begin
                        ln_gp_we   <= 1'b0;
                        cnt        <= 16'd0;
                        ln_in_we   <= 1'b1;
                        ln_in_addr <= 13'd0;
                        ln_in_data <= r1_buf[0];
                        state      <= S_LN1I;
                    end else begin
                        cnt         <= cnt + 16'd1;
                        ln_gp_addr  <= cnt[5:0] + 6'd1;
                        ln_gp_gamma <= ln_g[0][cnt[5:0] + 6'd1];
                        ln_gp_beta  <= ln_b[0][cnt[5:0] + 6'd1];
                    end
                end

                S_LN1I: begin
                    if (cnt == TACT-1) begin
                        ln_in_we <= 1'b0;
                        cnt      <= 16'd0;
                        ln_start <= 1'b1;
                        state    <= S_LN1;
                    end else begin
                        cnt        <= cnt + 16'd1;
                        ln_in_addr <= cnt[12:0] + 13'd1;
                        ln_in_data <= r1_buf[cnt[12:0] + 13'd1];
                    end
                end

                S_LN1: begin
                    ln_start <= 1'b0;
                    if (ln_done) begin
                        cnt     <= 16'd0;
                        state   <= S_FFN1I;
                    end
                end

                S_FFN1I: begin
                    if (cnt == TACT-4) begin
                        cnt      <= 16'd0;
                        f1_start <= 1'b1;
                        state    <= S_FFN1;
                    end else begin
                        cnt <= cnt + 16'd4;
                    end
                end

                S_FFN1: begin
                    f1_start <= 1'b0;
                    if (f1_done) begin
                        gelu_valid <= 1'b1;
                        gelu_x0    <= $signed(h_buf[0]);
                        gelu_x1    <= $signed(h_buf[1]);
                        gelu_x2    <= $signed(h_buf[2]);
                        gelu_x3    <= $signed(h_buf[3]);
                        gelu_wr    <= 15'd0;
                        hcnt       <= 16'd4;
                        state      <= S_GELU;
                    end
                end

                S_GELU: begin
                    if (hcnt == HACT) begin
                        gelu_valid <= 1'b0;
                        state      <= S_GELUD;
                    end else begin
                        gelu_x0 <= $signed(h_buf[hcnt[14:0]]);
                        gelu_x1 <= $signed(h_buf[hcnt[14:0] + 15'd1]);
                        gelu_x2 <= $signed(h_buf[hcnt[14:0] + 15'd2]);
                        gelu_x3 <= $signed(h_buf[hcnt[14:0] + 15'd3]);
                        hcnt    <= hcnt + 16'd4;
                    end
                end

                S_GELUD: begin
                    if (gelu_wr == HACT) begin
                        cnt     <= 16'd0;
                        state   <= S_FFN2I;
                    end
                end

                S_FFN2I: begin
                    if (cnt == HACT-4) begin
                        cnt      <= 16'd0;
                        f2_start <= 1'b1;
                        state    <= S_FFN2;
                    end else begin
                        cnt <= cnt + 16'd4;
                    end
                end

                S_FFN2: begin
                    f2_start <= 1'b0;
                    if (f2_done) begin
                        cnt   <= 16'd0;
                        state <= S_ALIGN2;
                    end
                end

                S_ALIGN2: begin
                    if (cnt >= TACT-4) begin
                        cnt         <= 16'd0;
                        ln_gp_we    <= 1'b1;
                        ln_gp_addr  <= 6'd0;
                        ln_gp_gamma <= ln_g[1][0];
                        ln_gp_beta  <= ln_b[1][0];
                        state       <= S_LN2P;
                    end else begin
                        cnt <= cnt + 16'd4;
                    end
                end

                S_LN2P: begin
                    if (cnt == D-1) begin
                        ln_gp_we   <= 1'b0;
                        cnt        <= 16'd0;
                        ln_in_we   <= 1'b1;
                        ln_in_addr <= 13'd0;
                        ln_in_data <= r2_buf[0];
                        state      <= S_LN2I;
                    end else begin
                        cnt         <= cnt + 16'd1;
                        ln_gp_addr  <= cnt[5:0] + 6'd1;
                        ln_gp_gamma <= ln_g[1][cnt[5:0] + 6'd1];
                        ln_gp_beta  <= ln_b[1][cnt[5:0] + 6'd1];
                    end
                end

                S_LN2I: begin
                    if (cnt == TACT-1) begin
                        ln_in_we <= 1'b0;
                        cnt      <= 16'd0;
                        ln_start <= 1'b1;
                        state    <= S_LN2;
                    end else begin
                        cnt        <= cnt + 16'd1;
                        ln_in_addr <= cnt[12:0] + 13'd1;
                        ln_in_data <= r2_buf[cnt[12:0] + 13'd1];
                    end
                end

                S_LN2: begin
                    ln_start <= 1'b0;
                    if (ln_done) begin
                        wait_cnt <= 4'd0;
                        state    <= S_DONE;
                    end
                end

                S_DONE: begin
                    done <= 1'b1;
                    if (start && !start_d) begin
                        // re-arm directly so a one-cycle start pulse is never missed
                        done        <= 1'b0;
                        wait_cnt    <= 4'd0;
                        cnt         <= 16'd0;
                        ln_eps      <= p_ln_eps;
                        at_start    <= 1'b1;
                        state       <= S_ATTN;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
