`timescale 1ns / 1ps
// Full attention block: x -> QKV -> QK^T -> softmax -> AV -> O projection.
//
// Parameters are preloaded through the shared p_* ports (sel: 0=Q 1=K 2=V 3=O).
// Operand buffers live here; the sub-blocks were verified individually.
//
// Result stream: out_buf, 4 int8 channels per 32-bit word, addr = t*16 + g.
module kwt_attention (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    // x input (99x64 int8)
    input  wire               x_we,
    input  wire [12:0]        x_addr,
    input  wire [7:0]         x_data,

    // parameter load: weights (int4) and bias/multiplier
    input  wire               p_wgt_we,
    input  wire [1:0]         p_wgt_sel,
    input  wire [13:0]        p_wgt_addr,
    input  wire [3:0]         p_wgt_data,
    input  wire               p_wgt_we16,
    input  wire [63:0]        p_wgt_data16,
    input  wire               p_bp_we,
    input  wire [1:0]         p_bp_sel,
    input  wire [7:0]         p_bp_addr,
    input  wire signed [31:0] p_bp_bias,
    input  wire signed [31:0] p_bp_m,

    // attention scale folded into the QK^T requantiser
    input  wire signed [31:0] m_score,
    input  wire signed [31:0] m_ctx,

    // output stream
    output reg                out_we,
    output reg  [12:0]        out_addr,
    output reg  [31:0]        out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam TOK   = 99;
    localparam D     = 64;
    localparam TACT  = TOK*D;        // 6336
    localparam NQ    = TOK*(D/4);    // 1584  (4 int8 per word)
    localparam NSC   = TOK*25;       // 2475  (4 int16 per word)
    localparam NP    = TOK*TOK;      // 9801

    // ------------------------------------------------------------------
    // operand buffers
    // ------------------------------------------------------------------
    reg [7:0]  x_buf     [0:TACT-1];
    reg [7:0]  q_buf     [0:TACT-1];
    reg [7:0]  k_buf     [0:TACT+3];
    reg [7:0]  v_buf     [0:TACT+195];
    reg [15:0] score_buf [0:TOK*100-1];
    reg [7:0]  p_buf     [0:NP+3];
    reg [7:0]  ctx_buf   [0:TACT-1];
    reg [6:0]  sm_row;

    always @(posedge clk) begin
        if (x_we) x_buf[x_addr] <= x_data;
    end

    // ------------------------------------------------------------------
    // parameter distribution
    // ------------------------------------------------------------------
    wire pQ = p_wgt_we && (p_wgt_sel == 2'd0);
    wire pK = p_wgt_we && (p_wgt_sel == 2'd1);
    wire pV = p_wgt_we && (p_wgt_sel == 2'd2);
    wire pO = p_wgt_we && (p_wgt_sel == 2'd3);
    wire pQ16 = p_wgt_we16 && (p_wgt_sel == 2'd0);
    wire pK16 = p_wgt_we16 && (p_wgt_sel == 2'd1);
    wire pV16 = p_wgt_we16 && (p_wgt_sel == 2'd2);
    wire pO16 = p_wgt_we16 && (p_wgt_sel == 2'd3);
    wire bQ = p_bp_we && (p_bp_sel == 2'd0);
    wire bK = p_bp_we && (p_bp_sel == 2'd1);
    wire bV = p_bp_we && (p_bp_sel == 2'd2);
    wire bO = p_bp_we && (p_bp_sel == 2'd3);

    // ------------------------------------------------------------------
    // stage 1: QKV
    // ------------------------------------------------------------------
    localparam S_IDLE  = 4'd0;
    localparam S_XLOAD = 4'd1;
    localparam S_QKV   = 4'd2;
    localparam S_SCORE = 4'd3;
    localparam S_SMLD  = 4'd4;
    localparam S_SM    = 4'd5;
    localparam S_AV    = 4'd6;
    localparam S_OLD   = 4'd7;
    localparam S_OPRJ  = 4'd8;
    localparam S_DONE  = 4'd9;

    reg [3:0]  state;
    reg [13:0] cnt;

    // x is streamed into all three projection engines four bytes at a time
    wire        a_we   = 1'b0;
    wire [12:0] a_addr = cnt[12:0];
    wire [7:0]  a_data = 8'd0;
    wire        a_we4  = (state == S_XLOAD);
    wire [31:0] a_data32 = {x_buf[cnt[12:0] + 13'd3], x_buf[cnt[12:0] + 13'd2],
                            x_buf[cnt[12:0] + 13'd1], x_buf[cnt[12:0]]};
    reg         qkv_start;
    wire        qkv_done;

    wire        q_out_we, k_out_we, v_out_we;
    wire [12:0] q_out_addr, k_out_addr, v_out_addr;
    wire [31:0] q_out_data, k_out_data, v_out_data;

    // scratch activation register (one shared stream into all three engines)
    reg [7:0] a_hold;

    kwt_attn_qkv u_qkv (
        .clk(clk), .rst_n(rst_n), .start(qkv_start),
        .q_act_we(a_we), .q_act_addr(a_addr), .q_act_data(a_data),
        .q_act_we4(a_we4), .q_act_data32(a_data32),
        .q_wgt_we(pQ), .q_wgt_addr(p_wgt_addr), .q_wgt_data(p_wgt_data),
        .q_wgt_we16(pQ16), .q_wgt_data16(p_wgt_data16),
        .q_bp_we(bQ), .q_bp_addr(p_bp_addr), .q_bp_bias(p_bp_bias), .q_bp_m(p_bp_m),
        .q_out_we(q_out_we), .q_out_addr(q_out_addr), .q_out_data(q_out_data),
        .k_act_we(a_we), .k_act_addr(a_addr), .k_act_data(a_data),
        .k_act_we4(a_we4), .k_act_data32(a_data32),
        .k_wgt_we(pK), .k_wgt_addr(p_wgt_addr), .k_wgt_data(p_wgt_data),
        .k_wgt_we16(pK16), .k_wgt_data16(p_wgt_data16),
        .k_bp_we(bK), .k_bp_addr(p_bp_addr), .k_bp_bias(p_bp_bias), .k_bp_m(p_bp_m),
        .k_out_we(k_out_we), .k_out_addr(k_out_addr), .k_out_data(k_out_data),
        .v_act_we(a_we), .v_act_addr(a_addr), .v_act_data(a_data),
        .v_act_we4(a_we4), .v_act_data32(a_data32),
        .v_wgt_we(pV), .v_wgt_addr(p_wgt_addr), .v_wgt_data(p_wgt_data),
        .v_wgt_we16(pV16), .v_wgt_data16(p_wgt_data16),
        .v_bp_we(bV), .v_bp_addr(p_bp_addr), .v_bp_bias(p_bp_bias), .v_bp_m(p_bp_m),
        .v_out_we(v_out_we), .v_out_addr(v_out_addr), .v_out_data(v_out_data),
        .done(qkv_done), .cycle_count()
    );

    // unpack 4 int8 channels per word
    always @(posedge clk) begin
        if (q_out_we) begin
            q_buf[{q_out_addr, 2'b00}] <= q_out_data[7:0];
            q_buf[{q_out_addr, 2'b01}] <= q_out_data[15:8];
            q_buf[{q_out_addr, 2'b10}] <= q_out_data[23:16];
            q_buf[{q_out_addr, 2'b11}] <= q_out_data[31:24];
        end
        if (k_out_we) begin
            k_buf[{k_out_addr, 2'b00}] <= k_out_data[7:0];
            k_buf[{k_out_addr, 2'b01}] <= k_out_data[15:8];
            k_buf[{k_out_addr, 2'b10}] <= k_out_data[23:16];
            k_buf[{k_out_addr, 2'b11}] <= k_out_data[31:24];
        end
        if (v_out_we) begin
            v_buf[{v_out_addr, 2'b00}] <= v_out_data[7:0];
            v_buf[{v_out_addr, 2'b01}] <= v_out_data[15:8];
            v_buf[{v_out_addr, 2'b10}] <= v_out_data[23:16];
            v_buf[{v_out_addr, 2'b11}] <= v_out_data[31:24];
        end
    end

    // ------------------------------------------------------------------
    // stage 2: QK^T
    // ------------------------------------------------------------------
    reg         sc_start;
    wire        sc_done;
    wire [12:0] sc_q_addr, sc_k_addr;
    wire [12:0] sc_out_addr;
    wire [63:0] sc_out_data;
    wire        sc_out_we;

    kwt_attn_score u_score (
        .clk(clk), .rst_n(rst_n), .start(sc_start),
        .q_rd_addr(sc_q_addr), .q_rd_data4({q_buf[sc_q_addr + 13'd3],
                                            q_buf[sc_q_addr + 13'd2],
                                            q_buf[sc_q_addr + 13'd1],
                                            q_buf[sc_q_addr]}),
        .k_rd_addr(sc_k_addr),
        .k_rd_data4({k_buf[sc_k_addr + 13'd3], k_buf[sc_k_addr + 13'd2],
                     k_buf[sc_k_addr + 13'd1], k_buf[sc_k_addr]}),
        .m_we(1'b1), .m_data(m_score),
        .out_we(sc_out_we), .out_addr(sc_out_addr), .out_data(sc_out_data),
        .done(sc_done), .cycle_count()
    );

    // unpack 4 int16 per word
    always @(posedge clk) begin
        if (sc_out_we) begin
            score_buf[{sc_out_addr, 2'b00}] <= sc_out_data[15:0];
            score_buf[{sc_out_addr, 2'b01}] <= sc_out_data[31:16];
            score_buf[{sc_out_addr, 2'b10}] <= sc_out_data[47:32];
            score_buf[{sc_out_addr, 2'b11}] <= sc_out_data[63:48];
        end
    end

    // ------------------------------------------------------------------
    // stage 3: softmax
    // ------------------------------------------------------------------
    reg         sm_start;
    reg         s_we;
    reg  [6:0]  s_addr;
    reg  [15:0] sd0, sd1, sd2, sd3;
    wire        sm_out_we;
    wire [6:0]  sm_out_addr;
    wire [7:0]  so0, so1, so2, so3;
    wire        d0, d1, d2, d3;
    wire        sm_done = d0 & d1 & d2 & d3;

    kwt_softmax #(.N(TOK)) u_sm0 (
        .clk(clk), .rst_n(rst_n), .start(sm_start),
        .s_we(s_we), .s_addr(s_addr), .s_data(sd0),
        .out_we(sm_out_we), .out_addr(sm_out_addr), .out_data(so0),
        .done(d0), .cycle_count()
    );
    kwt_softmax #(.N(TOK)) u_sm1 (
        .clk(clk), .rst_n(rst_n), .start(sm_start),
        .s_we(s_we), .s_addr(s_addr), .s_data(sd1),
        .out_we(), .out_addr(), .out_data(so1),
        .done(d1), .cycle_count()
    );
    kwt_softmax #(.N(TOK)) u_sm2 (
        .clk(clk), .rst_n(rst_n), .start(sm_start),
        .s_we(s_we), .s_addr(s_addr), .s_data(sd2),
        .out_we(), .out_addr(), .out_data(so2),
        .done(d2), .cycle_count()
    );
    kwt_softmax #(.N(TOK)) u_sm3 (
        .clk(clk), .rst_n(rst_n), .start(sm_start),
        .s_we(s_we), .s_addr(s_addr), .s_data(sd3),
        .out_we(), .out_addr(), .out_data(so3),
        .done(d3), .cycle_count()
    );

    always @(posedge clk) begin
        if (sm_out_we) begin
            if (sm_row          < TOK) p_buf[{7'd0, sm_row}          * TOK + sm_out_addr] <= so0;
            if (sm_row + 7'd1   < TOK) p_buf[{7'd0, sm_row + 7'd1}   * TOK + sm_out_addr] <= so1;
            if (sm_row + 7'd2   < TOK) p_buf[{7'd0, sm_row + 7'd2}   * TOK + sm_out_addr] <= so2;
            if (sm_row + 7'd3   < TOK) p_buf[{7'd0, sm_row + 7'd3}   * TOK + sm_out_addr] <= so3;
        end
    end

    // ------------------------------------------------------------------
    // stage 4: AV
    // ------------------------------------------------------------------
    reg         av_start;
    wire        av_done;
    wire [13:0] av_p_addr;
    wire [12:0] av_v_addr;
    wire [12:0] av_out_addr;
    wire [31:0] av_out_data;
    wire        av_out_we;

    kwt_attn_av u_av (
        .clk(clk), .rst_n(rst_n), .start(av_start),
        .p_rd_addr(av_p_addr),
        .p_rd_data4({p_buf[av_p_addr + 14'd3], p_buf[av_p_addr + 14'd2],
                     p_buf[av_p_addr + 14'd1], p_buf[av_p_addr]}),
        .v_rd_addr(av_v_addr),
        .v_rd_data4({v_buf[av_v_addr + 13'd192], v_buf[av_v_addr + 13'd128],
                     v_buf[av_v_addr + 13'd64],  v_buf[av_v_addr]}),
        .m_we(1'b1), .m_data(m_ctx),
        .out_we(av_out_we), .out_addr(av_out_addr), .out_data(av_out_data),
        .done(av_done), .cycle_count()
    );

    always @(posedge clk) begin
        if (av_out_we) begin
            ctx_buf[{av_out_addr, 2'b00}] <= av_out_data[7:0];
            ctx_buf[{av_out_addr, 2'b01}] <= av_out_data[15:8];
            ctx_buf[{av_out_addr, 2'b10}] <= av_out_data[23:16];
            ctx_buf[{av_out_addr, 2'b11}] <= av_out_data[31:24];
        end
    end

    // ------------------------------------------------------------------
    // stage 5: O projection
    // ------------------------------------------------------------------
    reg         o_start;
    wire        o_done;
    reg         o_we;
    reg  [12:0] o_addr;
    reg  [7:0]  o_data;
    wire [12:0] o_out_addr;
    wire [31:0] o_out_data;
    wire        o_out_we;

    kwt_gemm_engine #(
        .IN_DIM(D), .OUT_DIM(D), .TOKENS(TOK), .WB(4), .OUT_BITS(8),
        .AW_ACT(13), .AW_WGT(14), .AW_BP(8), .AW_OUT(13)
    ) u_oproj (
        .clk(clk), .rst_n(rst_n), .start(o_start),
        .act_we(o_we), .act_addr(o_addr), .act_data(o_data),
        .act_we4(1'b0), .act_data32(32'd0),
        .wgt_we(pO), .wgt_addr(p_wgt_addr), .wgt_data(p_wgt_data),
        .wgt_we16(pO16), .wgt_data16(p_wgt_data16), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(bO), .bp_addr(p_bp_addr), .bp_bias(p_bp_bias), .bp_m(p_bp_m),
        .out_we(o_out_we), .out_addr(o_out_addr), .out_data(o_out_data),
        .done(o_done), .cycle_count()
    );

    always @(posedge clk) begin
        if (o_out_we) begin
            out_we   <= 1'b1;
            out_addr <= o_out_addr;
            out_data <= o_out_data;
        end else begin
            out_we <= 1'b0;
        end
    end

    // ------------------------------------------------------------------
    // control
    // ------------------------------------------------------------------
    reg [6:0]  ld_row;
    reg [6:0]  ld_col;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            cnt         <= 14'd0;
            ld_row      <= 7'd0;
            ld_col      <= 7'd0;
            sm_row      <= 7'd0;
            qkv_start   <= 1'b0;
            sc_start    <= 1'b0;
            sm_start    <= 1'b0;
            av_start    <= 1'b0;
            o_start     <= 1'b0;
            s_we        <= 1'b0;
            s_addr      <= 7'd0;
            sd0         <= 16'd0;
            sd1         <= 16'd0;
            sd2         <= 16'd0;
            sd3         <= 16'd0;
            o_we        <= 1'b0;
            o_addr      <= 13'd0;
            o_data      <= 8'd0;
            done        <= 1'b0;
            cycle_count <= 32'd0;
        end else begin
            cycle_count <= cycle_count + 32'd1;
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    cnt  <= 14'd0;
                    if (start) begin
                        cycle_count <= 32'd0;
                        state       <= S_XLOAD;
                    end
                end

                // stream x into the three projection engines, four bytes per cycle
                S_XLOAD: begin
                    if (cnt == TACT-4) begin
                        cnt       <= 14'd0;
                        qkv_start <= 1'b1;
                        state     <= S_QKV;
                    end else begin
                        cnt <= cnt + 14'd4;
                    end
                end

                S_QKV: begin
                    qkv_start <= 1'b0;
                    if (qkv_done) begin
                        sc_start <= 1'b1;
                        state    <= S_SCORE;
                    end
                end

                S_SCORE: begin
                    sc_start <= 1'b0;
                    if (sc_done) begin
                        sm_row <= 7'd0;
                        ld_col <= 7'd0;
                        s_we   <= 1'b1;
                        s_addr <= 7'd0;
                        sd0    <= score_buf[0];
                        sd1    <= score_buf[100];
                        sd2    <= score_buf[200];
                        sd3    <= score_buf[300];
                        state  <= S_SMLD;
                    end
                end

                // softmax handles 4 rows per start/done cycle (99 = 24*4 + 3)
                S_SMLD: begin
                    if (ld_col == TOK-1) begin
                        ld_col   <= 7'd0;
                        s_we     <= 1'b0;
                        sm_start <= 1'b1;
                        state    <= S_SM;
                    end else begin
                        ld_col <= ld_col + 7'd1;
                        s_addr <= ld_col + 7'd1;
                        sd0    <= score_buf[{7'd0, sm_row}        * 100 + ld_col + 7'd1];
                        sd1    <= (sm_row + 7'd1 < TOK)
                                  ? score_buf[{7'd0, sm_row + 7'd1} * 100 + ld_col + 7'd1] : 16'sd0;
                        sd2    <= (sm_row + 7'd2 < TOK)
                                  ? score_buf[{7'd0, sm_row + 7'd2} * 100 + ld_col + 7'd1] : 16'sd0;
                        sd3    <= (sm_row + 7'd3 < TOK)
                                  ? score_buf[{7'd0, sm_row + 7'd3} * 100 + ld_col + 7'd1] : 16'sd0;
                    end
                end

                S_SM: begin
                    sm_start <= 1'b0;
                    if (sm_done) begin
                        if (sm_row + 7'd4 >= TOK) begin
                            av_start <= 1'b1;
                            state    <= S_AV;
                        end else begin
                            sm_row <= sm_row + 7'd4;
                            ld_col <= 7'd0;
                            s_we   <= 1'b1;
                            s_addr <= 7'd0;
                            sd0    <= score_buf[{7'd0, sm_row + 7'd4} * 100];
                            sd1    <= (sm_row + 7'd5 < TOK)
                                      ? score_buf[{7'd0, sm_row + 7'd5} * 100] : 16'sd0;
                            sd2    <= (sm_row + 7'd6 < TOK)
                                      ? score_buf[{7'd0, sm_row + 7'd6} * 100] : 16'sd0;
                            sd3    <= (sm_row + 7'd7 < TOK)
                                      ? score_buf[{7'd0, sm_row + 7'd7} * 100] : 16'sd0;
                            state  <= S_SMLD;
                        end
                    end
                end

                S_AV: begin
                    av_start <= 1'b0;
                    if (av_done) begin
                        cnt    <= 14'd0;
                        o_we   <= 1'b1;
                        o_addr <= 13'd0;
                        o_data <= ctx_buf[0];
                        state  <= S_OLD;
                    end
                end

                S_OLD: begin
                    if (cnt == TACT-1) begin
                        o_we    <= 1'b0;
                        cnt     <= 14'd0;
                        o_start <= 1'b1;
                        state   <= S_OPRJ;
                    end else begin
                        o_addr <= cnt[12:0] + 13'd1;
                        o_data <= ctx_buf[cnt[12:0] + 13'd1];
                        cnt    <= cnt + 14'd1;
                    end
                end

                S_OPRJ: begin
                    o_start <= 1'b0;
                    if (o_done) state <= S_DONE;
                end

                S_DONE: begin
                    done <= 1'b1;
                    if (!start) state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
