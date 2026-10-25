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

    // ------------------------------------------------------------------
    // operand storage: standard dual-port SRAMs with width packing
    //
    //   act: 16 int8 per 128-bit word -> a 64-wide fetch is four words
    //   wgt: 64 elements per word     -> 4 channels x 64 inputs is four words
    //
    // Each buffer uses two kwt_sram_2r1w macros (2R1W each), so the four
    // parallel operand fetches only need standard dual-port primitives.
    // The rules only allow single/dual-port macros, so no custom many-port
    // array is used anywhere.
    // ------------------------------------------------------------------
    localparam AGRP    = 16;                    // int8 per activation word
    localparam AWD     = TOTAL_ACT / AGRP;
    localparam AW_ACTL = $clog2(AWD);
    localparam WGRP    = 64;                    // elements per weight word
    localparam WWGT    = WGRP * WB;
    localparam AWDW    = TOTAL_WGT / WGRP;
    localparam AW_WGTL = $clog2(AWDW);
    localparam KPG     = IN_DIM / 64;           // weight words per channel/segment
    localparam LOG2_IN = $clog2(IN_DIM);
    localparam LOG2_K  = $clog2(KPG);
    localparam AW_CG   = $clog2(OUT_DIM);       // channel index width

    reg signed [31:0] bias_buf [0:OUT_DIM-1];
    reg signed [31:0] m_buf    [0:OUT_DIM-1];

    always @(posedge clk) begin
        if (bp_we) begin
            bias_buf[bp_addr] <= bp_bias;
            m_buf[bp_addr]    <= bp_m;
        end
    end

    // ---- activation write port: byte lanes inside a 128-bit word ----
    // bank interleaves on address bit4 (32 bytes per bank pair), so the
    // internal address is the global word index shifted right by one
    wire [AW_ACTL-1:0] act_w_word = act_addr >> 5;
    wire [3:0]         act_w_lane = act_addr[3:0];
    wire               act_w_bank = act_addr[4];
    wire               act_wr     = act_we | act_we4;

    reg  [127:0]       act_wdata;
    reg  [15:0]        act_wmask;
    always @(*) begin
        act_wdata = 128'd0;
        act_wmask = 16'd0;
        if (act_we4) begin
            act_wdata = {96'd0, act_data32} << (act_w_lane*8);
            act_wmask = 16'h000F << act_w_lane;
        end else if (act_we) begin
            act_wdata = {120'd0, act_data} << (act_w_lane*8);
            act_wmask = 16'h0001 << act_w_lane;
        end
    end

    // ---- weight write port: element lanes inside a 64-element word ----
    // bank = output channel parity, so a 4-channel fetch hits each bank twice
    wire [AW_CG-1:0]   wgt_cglob  = wgt_addr >> LOG2_IN;
    wire               wgt_wbank  = wgt_cglob[0];
    wire [AW_WGTL-1:0] wgt_wint   = (((wgt_cglob >> 2) << (LOG2_K+1)) |
                                     (((wgt_cglob >> 1) & 1'b1) << LOG2_K) |
                                     ((wgt_addr >> 6) & (KPG-1)));
    wire [5:0]         wgt_woff   = wgt_addr[5:0];
    wire               wgt_wr     = wgt_we | wgt_we4 | wgt_we16;

    reg  [WWGT-1:0]    wgt_wdata;
    reg  [63:0]        wgt_wmask;
    always @(*) begin
        wgt_wdata = {WWGT{1'b0}};
        wgt_wmask = 64'd0;
        if (wgt_we16) begin
            wgt_wdata = {{(WWGT-64){1'b0}}, wgt_data16} << (wgt_woff*WB);
            wgt_wmask = 64'h0000_0000_0000_FFFF << wgt_woff;
        end else if (wgt_we4) begin
            wgt_wdata = {{(WWGT-8*WB){1'b0}}, wgt_data_w4} << (wgt_woff*WB);
            wgt_wmask = 64'h0000_0000_0000_000F << wgt_woff;
        end else if (wgt_we) begin
            wgt_wdata = {{(WWGT-WB){1'b0}}, wgt_data} << (wgt_woff*WB);
            wgt_wmask = 64'h0000_0000_0000_0001 << wgt_woff;
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
    reg [6:0] t_pipe_q;          // one-cycle delayed copy for index pairing
    reg [5:0] g_pipe_q;
    reg [6:0] t_out;
    reg [5:0] g_out;

    wire [6:0] t_issel = (SEGS == 1) ? t_pipe : t_lat;
    wire [5:0] g_issel = (SEGS == 1) ? g_pipe : g_lat;

    // ---- four parallel operand reads from two 2R1W banks each ----
    // act word base is a multiple of four, so bank = word bit0 gives two
    // distinct internal addresses per bank for the four requested words
    wire [AW_ACTL-1:0] act_r_base = t_issel*(IN_DIM/AGRP) + seg_lat*4;
    wire [AW_ACTL-1:0] act_r_lo   = act_r_base >> 1;
    wire [AW_ACTL-1:0] act_r_hi   = (act_r_base >> 1) + 1'b1;

    wire [127:0] act_q_b0l, act_q_b0h, act_q_b1l, act_q_b1h;

    kwt_sram_2r1w #(.DW(128), .AW(AW_ACTL), .SW(8), .MASKW(16)) u_act_b0 (
        .clk(clk),
        .a_addr(act_r_lo), .a_q(act_q_b0l),
        .b_addr(act_r_hi), .b_q(act_q_b0h),
        .we(act_wr & ~act_w_bank), .w_addr(act_w_word),
        .w_data(act_wdata), .w_mask(act_wmask)
    );
    kwt_sram_2r1w #(.DW(128), .AW(AW_ACTL), .SW(8), .MASKW(16)) u_act_b1 (
        .clk(clk),
        .a_addr(act_r_lo), .a_q(act_q_b1l),
        .b_addr(act_r_hi), .b_q(act_q_b1h),
        .we(act_wr &  act_w_bank), .w_addr(act_w_word),
        .w_data(act_wdata), .w_mask(act_wmask)
    );

    // k=0 -> b0.lo, k=1 -> b1.lo, k=2 -> b0.hi, k=3 -> b1.hi
    wire [511:0] act_flat = {act_q_b1h, act_q_b0h, act_q_b1l, act_q_b0l};

    // weight word address: channel group g, sub-channel 0/1 (hi) and segment
    wire [AW_WGTL-1:0] wgt_r_lo = g_issel*(2*KPG) + seg_lat;
    wire [AW_WGTL-1:0] wgt_r_hi = wgt_r_lo + KPG;

    wire [WWGT-1:0] wgt_q_b0l, wgt_q_b0h, wgt_q_b1l, wgt_q_b1h;

    kwt_sram_2r1w #(.DW(WWGT), .AW(AW_WGTL), .SW(WB), .MASKW(64)) u_wgt_b0 (
        .clk(clk),
        .a_addr(wgt_r_lo), .a_q(wgt_q_b0l),
        .b_addr(wgt_r_hi), .b_q(wgt_q_b0h),
        .we(wgt_wr & ~wgt_wbank), .w_addr(wgt_wint),
        .w_data(wgt_wdata), .w_mask(wgt_wmask)
    );
    kwt_sram_2r1w #(.DW(WWGT), .AW(AW_WGTL), .SW(WB), .MASKW(64)) u_wgt_b1 (
        .clk(clk),
        .a_addr(wgt_r_lo), .a_q(wgt_q_b1l),
        .b_addr(wgt_r_hi), .b_q(wgt_q_b1h),
        .we(wgt_wr &  wgt_wbank), .w_addr(wgt_wint),
        .w_data(wgt_wdata), .w_mask(wgt_wmask)
    );

    // c=0 -> b0.lo, c=1 -> b1.lo, c=2 -> b0.hi, c=3 -> b1.hi
    wire [4*WWGT-1:0] wgt_flat = {wgt_q_b1h, wgt_q_b0h, wgt_q_b1l, wgt_q_b0l};

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
    reg        flush_d;          // first drained group in S_FLUSH

    wire signed [31:0] acc0, acc1, acc2, acc3;
    wire               gemm_valid;
    wire               gemm_issue = (SEGS == 1) ? (state == S_PIPE)
                                                : (state == S_ISSUE);

    // The operand SRAMs return data one cycle after the address is presented,
    // so the MAC enable and the output index each trail the issue by one more
    // cycle than in the register-file version.
    reg                issue_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) issue_q <= 1'b0;
        else        issue_q <= gemm_issue;
    end

    reg signed [31:0]  acc0_r, acc1_r, acc2_r, acc3_r;

    kwt_gemm4 #(.WB(WB)) u_gemm (
        .clk      (clk),
        .rst_n    (rst_n),
        .valid_in (issue_q),
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
            t_pipe_q    <= 7'd0;
            g_pipe_q    <= 6'd0;
            t_out       <= 7'd0;
            g_out       <= 6'd0;
            flush_d     <= 1'b0;
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
                    t_pipe_q <= 7'd0;
                    g_pipe_q <= 6'd0;
                    t_out   <= 7'd0;
                    g_out   <= 6'd0;
                    flush_d <= 1'b0;
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
                    g_pipe_q <= g_pipe;
                    t_pipe_q <= t_pipe;
                    g_out <= g_pipe_q;
                    t_out <= t_pipe_q;
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
                    g_pipe_q <= g_pipe;
                    t_pipe_q <= t_pipe;
                    g_out <= g_pipe_q;
                    t_out <= t_pipe_q;
                    if (gemm_valid) begin
                        out_we   <= 1'b1;
                        out_addr <= t_out*GROUPS + g_out;
                        out_data <= {q3[OUT_BITS-1:0], q2[OUT_BITS-1:0],
                                     q1[OUT_BITS-1:0], q0[OUT_BITS-1:0]};
                        // two issue stages are still in flight, so drain both
                        if (flush_d) begin
                            flush_d <= 1'b0;
                            state   <= S_DONE;
                        end else begin
                            flush_d <= 1'b1;
                        end
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
