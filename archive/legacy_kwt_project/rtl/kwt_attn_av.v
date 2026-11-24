`timescale 1ns / 1ps
// Attention value stage: ctx = P * V
//
// P is 99x99 (softmax output), V is 99x64. Both are zero-padded to 128 so the
// GEMM engine sees IN_DIM=128 (two 64-wide segments) and OUT_DIM=64.
//
//   act[t*128 + i] = P[t, i]   (i < 99, else 0)
//   wgt[c*128 + i] = V[i, c]   (i < 99, else 0)
module kwt_attn_av (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    output wire [13:0]        p_rd_addr,     // 99*99, addr = t*99 + i
    input  wire [31:0]        p_rd_data4,    // four bytes from p_rd_addr

    output wire [12:0]        v_rd_addr,     // 99*64, addr = i*64 + c
    input  wire [31:0]        v_rd_data4,    // four successive channels

    input  wire               m_we,
    input  wire signed [31:0] m_data,

    output wire               out_we,
    output wire [12:0]        out_addr,
    output wire [31:0]        out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam TOK       = 99;
    localparam D         = 64;
    localparam IN_DIM    = 128;
    localparam OUT_DIM   = 64;
    localparam TOTAL_ACT = TOK * IN_DIM;     // 12672
    localparam TOTAL_WGT = OUT_DIM * IN_DIM; // 8192

    localparam S_IDLE   = 4'd0;
    localparam S_LOADPV = 4'd1;
    localparam S_LOADM  = 4'd3;
    localparam S_RUN    = 4'd4;
    localparam S_DONE   = 4'd5;

    reg [3:0]  state;
    reg [6:0]  row_p, col_p;   // P side: token / column
    reg [6:0]  row_v, col_v;   // V side: output channel / column
    reg        v_on;           // V loader still active
    reg        p_done;         // P loader finished
    reg [13:0] cnt;

    // Both loaders run in the same cycle. P writes four bytes at a time;
    // V is a transposed gather and stays one byte per cycle. Addresses and
    // data are combinational so writes land with no one-cycle skew.
    wire [13:0] act_addr = {row_p, 7'd0} + {7'd0, col_p};
    wire [31:0] p_word   = ((col_p + 7'd3) < TOK) ? p_rd_data4
                         : (col_p < TOK)          ? (p_rd_data4 & 32'h00FF_FFFF)
                         :                          32'd0;
    wire [12:0] wgt_addr = {row_v[5:0], 7'd0} + {6'd0, col_v};
    wire [31:0] v_word   = ((col_v + 7'd3) < TOK) ? v_rd_data4
                         : (col_v < TOK)          ? (v_rd_data4 & 32'h00FF_FFFF)
                         :                          32'd0;
    wire        act_we4  = (state == S_LOADPV) && !p_done;
    wire        act_we   = 1'b0;
    wire        wgt_we4  = (state == S_LOADPV) && v_on;
    wire        wgt_we   = 1'b0;

    assign p_rd_addr = ((state == S_LOADPV) && (col_p < TOK))
                       ? (row_p * TOK + col_p) : 14'd0;
    assign v_rd_addr = ((state == S_LOADPV) && v_on && (col_v < TOK))
                       ? (col_v * D + row_v) : 13'd0;

    wire        bp_we   = (state == S_LOADM);
    wire [7:0]  bp_addr = cnt[7:0];
    wire signed [31:0] bp_bias = 32'sd0;
    wire signed [31:0] bp_m    = m_data;

    reg  engine_start;
    wire engine_done;

    kwt_gemm_engine #(
        .IN_DIM(IN_DIM), .OUT_DIM(OUT_DIM), .TOKENS(TOK),
        .WB(8), .OUT_BITS(8),
        .AW_ACT(14), .AW_WGT(13), .AW_BP(8), .AW_OUT(13)
    ) u_engine (
        .clk(clk), .rst_n(rst_n), .start(engine_start),
        .act_we(act_we), .act_addr(act_addr), .act_data(8'd0),
        .act_we4(act_we4), .act_data32(p_word),
        .wgt_we(wgt_we), .wgt_addr(wgt_addr), .wgt_data(8'd0),
        .wgt_we16(1'b0), .wgt_data16(64'd0), .wgt_we4(wgt_we4), .wgt_data_w4(v_word),
        .bp_we(bp_we), .bp_addr(bp_addr), .bp_bias(bp_bias), .bp_m(bp_m),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(engine_done), .cycle_count()
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= S_IDLE;
            row_p        <= 7'd0;
            col_p        <= 7'd0;
            row_v        <= 7'd0;
            col_v        <= 7'd0;
            v_on         <= 1'b0;
            p_done       <= 1'b0;
            cnt          <= 14'd0;
            engine_start <= 1'b0;
            done         <= 1'b0;
            cycle_count  <= 32'd0;
        end else begin
            cycle_count <= cycle_count + 32'd1;
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    row_p <= 7'd0;
                    col_p <= 7'd0;
                    row_v <= 7'd0;
                    col_v <= 7'd0;
                    if (start) begin
                        cycle_count <= 32'd0;
                        v_on        <= 1'b1;
                        p_done      <= 1'b0;
                        state       <= S_LOADPV;
                    end
                end

                // act[t*128 + i] = P[t, i]  (i < 99, else zero)
                // wgt[c*128 + i] = V[i, c]  (i < 99, else zero)
                // The two loaders touch disjoint buffers so they run together.
                // V needs 64 rows, P needs 99, so V finishes first.
                S_LOADPV: begin
                    if (v_on) begin
                        if (col_v == IN_DIM-4) begin
                            col_v <= 7'd0;
                            if (row_v == OUT_DIM-1) v_on  <= 1'b0;
                            else                    row_v <= row_v + 7'd1;
                        end else begin
                            col_v <= col_v + 7'd4;
                        end
                    end
                    if (!p_done) begin
                        if (col_p == IN_DIM-4) begin
                            col_p <= 7'd0;
                            if (row_p == TOK-1) begin
                                row_p  <= 7'd0;
                                cnt    <= 14'd0;
                                p_done <= 1'b1;
                            end else begin
                                row_p <= row_p + 7'd1;
                            end
                        end else begin
                            col_p <= col_p + 7'd4;
                        end
                    end
                    // leave only when both loaders are finished
                    if (p_done && !v_on) state <= S_LOADM;
                end

                S_LOADM: begin
                    if (cnt == OUT_DIM-1) begin
                        cnt          <= 14'd0;
                        engine_start <= 1'b1;
                        state        <= S_RUN;
                    end else begin
                        cnt <= cnt + 14'd1;
                    end
                end

                S_RUN: begin
                    engine_start <= 1'b0;
                    if (engine_done) state <= S_DONE;
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
