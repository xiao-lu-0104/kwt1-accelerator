`timescale 1ns / 1ps
// Parameterized GEMM engine for the KWT accelerator.
//
//   y[t, c] = sat8(((sum_i x[t,i] * w[i,c]) + bias[c]) * m[c] >> 31)
//
// IN_DIM must be a multiple of 64 (the MAC primitive width); 256 uses four
// segments with carry-over accumulation. OUT_DIM must be a multiple of 4.
//
// Result stream packs 4 int8 channels per 32-bit word:
//   out_addr = token*(OUT_DIM/4) + group, out_data = {ch+3, ch+2, ch+1, ch+0}
//
// Bit-exact reference: tools/fixed_sim.py (FixedLinear)
module kwt_gemm_engine #(
    parameter IN_DIM  = 64,
    parameter OUT_DIM = 256,
    parameter TOKENS  = 99,
    parameter WB      = 4,
    parameter OUT_BITS = 8,
    parameter AW_ACT  = $clog2(TOKENS*IN_DIM),
    parameter AW_WGT  = $clog2(OUT_DIM*IN_DIM),
    parameter AW_BP   = $clog2(OUT_DIM),
    parameter AW_OUT  = $clog2(TOKENS*(OUT_DIM/4))
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    input  wire               act_we,
    input  wire [AW_ACT-1:0]  act_addr,
    input  wire [7:0]         act_data,

    // wide activation load: writes 4 bytes starting at act_addr
    input  wire               act_we4,
    input  wire [31:0]        act_data32,

    input  wire               wgt_we,
    input  wire [AW_WGT-1:0]  wgt_addr,
    input  wire [WB-1:0]      wgt_data,

    // wide weight load: writes 16 nibbles starting at wgt_addr
    input  wire               wgt_we16,
    input  wire [63:0]        wgt_data16,

    // wide weight load: writes 4 entries starting at wgt_addr
    input  wire               wgt_we4,
    input  wire [8*WB-1:0]    wgt_data_w4,

    input  wire               bp_we,
    input  wire [AW_BP-1:0]   bp_addr,
    input  wire signed [31:0] bp_bias,
    input  wire signed [31:0] bp_m,

    output reg                out_we,
    output reg  [AW_OUT-1:0]  out_addr,
    output reg  [4*OUT_BITS-1:0] out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam TOTAL_ACT = TOKENS * IN_DIM;
    localparam TOTAL_WGT = OUT_DIM * IN_DIM;
    localparam GROUPS    = OUT_DIM / 4;
    localparam SEGS      = IN_DIM / 64;
    localparam LIM       = (1 << (OUT_BITS-1)) - 1;

    reg [7:0]  act_buf [0:TOTAL_ACT-1];
    reg [WB-1:0] wgt_buf [0:TOTAL_WGT-1];
    reg signed [31:0] bias_buf [0:OUT_DIM-1];
    reg signed [31:0] m_buf    [0:OUT_DIM-1];

    integer kk;
    always @(posedge clk) begin
        if (act_we) act_buf[act_addr] <= act_data;
        if (act_we4) begin
            for (kk = 0; kk < 4; kk = kk + 1)
                act_buf[act_addr + kk] <= act_data32[kk*8 +: 8];
        end
        if (wgt_we) wgt_buf[wgt_addr] <= wgt_data;
        if (wgt_we16) begin
            for (kk = 0; kk < 16; kk = kk + 1)
                wgt_buf[wgt_addr + kk] <= wgt_data16[kk*4 +: 4];
        end
        if (wgt_we4) begin
            for (kk = 0; kk < 4; kk = kk + 1)
                wgt_buf[wgt_addr + kk] <= wgt_data_w4[kk*WB +: WB];
        end
        if (bp_we) begin
            bias_buf[bp_addr] <= bp_bias;
            m_buf[bp_addr]    <= bp_m;
        end
    end

    function signed [31:0] requant(input signed [31:0] acc, input signed [31:0] m);
        reg signed [63:0] prod;
        reg signed [63:0] shifted;
        begin
            prod    = acc * m;
            shifted = (prod + 64'sd1073741824) >>> 31;
            if (shifted > LIM)
                requant = LIM;
            else if (shifted < -LIM)
                requant = -LIM;
            else
                requant = shifted[31:0];
        end
    endfunction

    // ------------------------------------------------------------------
    // operand gather
    // ------------------------------------------------------------------
    reg [6:0] t_lat;
    reg [5:0] g_lat;
    reg [1:0] seg_lat;
    // pipelined issue/output counters (SEGS==1 fast path)
    reg [6:0] t_pipe;
    reg [5:0] g_pipe;
    reg [6:0] t_out;
    reg [5:0] g_out;

    reg [511:0]  act_flat;
    reg [4*64*WB-1:0] wgt_flat;
    wire [6:0] t_issel = (SEGS == 1) ? t_pipe : t_lat;
    wire [5:0] g_issel = (SEGS == 1) ? g_pipe : g_lat;
    integer jj;
    always @(*) begin
        for (jj = 0; jj < 64; jj = jj + 1)
            act_flat[jj*8 +: 8] = act_buf[t_issel*IN_DIM + seg_lat*64 + jj];
        for (jj = 0; jj < 256; jj = jj + 1)
            wgt_flat[jj*WB +: WB] =
                wgt_buf[(g_issel*4 + (jj/64))*IN_DIM + seg_lat*64 + (jj%64)];
    end

    // ------------------------------------------------------------------
    // control
    // ------------------------------------------------------------------
    localparam S_IDLE  = 3'd0;
    localparam S_ISSUE = 3'd1;
    localparam S_CALC  = 3'd2;
    localparam S_DONE  = 3'd3;
    localparam S_PIPE  = 3'd4;
    localparam S_FLUSH = 3'd5;

    reg [2:0]  state;

    wire signed [31:0] acc0, acc1, acc2, acc3;
    wire               gemm_valid;
    wire               gemm_issue = (SEGS == 1) ? (state == S_PIPE)
                                                : (state == S_ISSUE);
    reg signed [31:0]  acc0_r, acc1_r, acc2_r, acc3_r;

    kwt_gemm4 #(.WB(WB)) u_gemm (
        .clk      (clk),
        .rst_n    (rst_n),
        .valid_in (gemm_issue),
        .act_flat (act_flat),
        .wgt_flat (wgt_flat),
        .acc_in0  (acc0_r),
        .acc_in1  (acc1_r),
        .acc_in2  (acc2_r),
        .acc_in3  (acc3_r),
        .acc0     (acc0),
        .acc1     (acc1),
        .acc2     (acc2),
        .acc3     (acc3),
        .valid_out(gemm_valid)
    );

    wire [5:0] g_sel = (SEGS == 1) ? g_out : g_lat;
    wire [6:0] t_sel = (SEGS == 1) ? t_out : t_lat;

    wire signed [31:0] q0 = requant(acc0 + bias_buf[g_sel*4 + 0], m_buf[g_sel*4 + 0]);
    wire signed [31:0] q1 = requant(acc1 + bias_buf[g_sel*4 + 1], m_buf[g_sel*4 + 1]);
    wire signed [31:0] q2 = requant(acc2 + bias_buf[g_sel*4 + 2], m_buf[g_sel*4 + 2]);
    wire signed [31:0] q3 = requant(acc3 + bias_buf[g_sel*4 + 3], m_buf[g_sel*4 + 3]);

    // ------------------------------------------------------------------
    // control
    // ------------------------------------------------------------------

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            t_lat       <= 7'd0;
            g_lat       <= 6'd0;
            seg_lat     <= 2'd0;
            t_pipe      <= 7'd0;
            g_pipe      <= 6'd0;
            t_out       <= 7'd0;
            g_out       <= 6'd0;
            acc0_r      <= 32'sd0;
            acc1_r      <= 32'sd0;
            acc2_r      <= 32'sd0;
            acc3_r      <= 32'sd0;
            out_we      <= 1'b0;
            out_addr    <= {AW_OUT{1'b0}};
            out_data    <= 32'd0;
            done        <= 1'b0;
            cycle_count <= 32'd0;
        end else begin
            out_we <= 1'b0;
            case (state)
                S_IDLE: begin
                    done    <= 1'b0;
                    t_lat   <= 7'd0;
                    g_lat   <= 6'd0;
                    seg_lat <= 2'd0;
                    t_pipe  <= 7'd0;
                    g_pipe  <= 6'd0;
                    t_out   <= 7'd0;
                    g_out   <= 6'd0;
                    acc0_r  <= 32'sd0;
                    acc1_r  <= 32'sd0;
                    acc2_r  <= 32'sd0;
                    acc3_r  <= 32'sd0;
                    if (start) begin
                        cycle_count <= 32'd0;
                        state       <= S_ISSUE;
                    end
                end

                S_ISSUE: begin
                    cycle_count <= cycle_count + 32'd1;
                    state       <= (SEGS == 1) ? S_PIPE : S_CALC;
                end

                // ---- single-segment fast path: one issue per cycle ----
                S_PIPE: begin
                    cycle_count <= cycle_count + 32'd1;
                    g_out <= g_pipe;
                    t_out <= t_pipe;
                    if (gemm_valid) begin
                        out_we   <= 1'b1;
                        out_addr <= t_out*GROUPS + g_out;
                        out_data <= {q3[OUT_BITS-1:0], q2[OUT_BITS-1:0],
                                     q1[OUT_BITS-1:0], q0[OUT_BITS-1:0]};
                    end
                    if (g_pipe == GROUPS-1) begin
                        if (t_pipe == TOKENS-1) begin
                            state <= S_FLUSH;      // keep g_pipe for the flush
                        end else begin
                            g_pipe <= 6'd0;
                            t_pipe <= t_pipe + 7'd1;
                        end
                    end else begin
                        g_pipe <= g_pipe + 6'd1;
                    end
                end

                S_FLUSH: begin
                    cycle_count <= cycle_count + 32'd1;
                    g_out <= g_pipe;
                    t_out <= t_pipe;
                    if (gemm_valid) begin
                        out_we   <= 1'b1;
                        out_addr <= t_out*GROUPS + g_out;
                        out_data <= {q3[OUT_BITS-1:0], q2[OUT_BITS-1:0],
                                     q1[OUT_BITS-1:0], q0[OUT_BITS-1:0]};
                        state    <= S_DONE;
                    end
                end

                S_CALC: begin
                    cycle_count <= cycle_count + 32'd1;
                    if (gemm_valid) begin
                        if (seg_lat == SEGS-1) begin
                            // final segment: requant and emit
                            out_we   <= 1'b1;
                            out_addr <= t_lat*GROUPS + g_lat;
                            out_data <= {q3[OUT_BITS-1:0], q2[OUT_BITS-1:0],
                                         q1[OUT_BITS-1:0], q0[OUT_BITS-1:0]};
                            acc0_r   <= 32'sd0;
                            acc1_r   <= 32'sd0;
                            acc2_r   <= 32'sd0;
                            acc3_r   <= 32'sd0;
                            seg_lat  <= 2'd0;
                            if (g_lat == GROUPS-1) begin
                                g_lat <= 6'd0;
                                if (t_lat == TOKENS-1) begin
                                    state <= S_DONE;
                                end else begin
                                    t_lat <= t_lat + 7'd1;
                                    state <= S_ISSUE;
                                end
                            end else begin
                                g_lat <= g_lat + 6'd1;
                                state <= S_ISSUE;
                            end
                        end else begin
                            // keep accumulating
                            acc0_r  <= acc0;
                            acc1_r  <= acc1;
                            acc2_r  <= acc2;
                            acc3_r  <= acc3;
                            seg_lat <= seg_lat + 2'd1;
                            state   <= S_ISSUE;
                        end
                    end
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
