`timescale 1ns / 1ps
// QK^T scoring stage.
//
// Consumes Q (99x64 int8) and K (99x64 int8) through external read ports,
// transposes K into the engine weight buffer, and produces a 99x100 int16
// score matrix (column 99 is padding).
//
// score = Q * K^T with the attention scale folded into m_score.
module kwt_attn_score (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    // Q source (read four bytes per cycle)
    output reg  [12:0]        q_rd_addr,
    input  wire [31:0]        q_rd_data4,

    // K source (read four bytes per cycle)
    output wire [12:0]        k_rd_addr,
    input  wire [31:0]        k_rd_data4,

    // per-channel multiplier (same value for all 100 channels)
    input  wire               m_we,
    input  wire signed [31:0] m_data,

    output wire               out_we,
    output wire [12:0]        out_addr,
    output wire [63:0]        out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam IN_DIM    = 64;
    localparam OUT_DIM   = 100;
    localparam TOKENS    = 99;
    localparam TOTAL_ACT = TOKENS * IN_DIM;    // 6336
    localparam TOTAL_WGT = OUT_DIM * IN_DIM;   // 6400

    localparam S_IDLE  = 4'd0;
    localparam S_LOADQ = 4'd1;
    localparam S_LOADK = 4'd2;
    localparam S_TRANS = 4'd3;
    localparam S_LOADM = 4'd4;
    localparam S_RUN   = 4'd5;
    localparam S_DONE  = 4'd6;

    reg [3:0]  state;
    reg [13:0] cnt;

    wire [7:0]  act_data = 8'd0;       // engine port kept quiet; wide loads used
    wire [12:0] act_addr = cnt[12:0];  // combinational: no one-cycle skew
    reg        wgt_we;
    wire [13:0] wgt_addr = (state == S_LOADK) ? cnt : 14'd0;
    reg [7:0]  wgt_data_r;
    wire [7:0] wgt_data = wgt_data_r;
    wire        wgt_we4   = (state == S_LOADK);
    wire [31:0] wgt_word4 = (cnt < TOTAL_ACT) ? k_rd_data4 : 32'd0;
    assign k_rd_addr = cnt[12:0];

    reg [7:0]  tc;      // output channel
    reg [6:0]  ti;      // input dim

    // multiplier/bias ports are combinational so address and data always
    // line up (no one-cycle skew)
    wire        bp_we   = (state == S_LOADM);
    wire [7:0]  bp_addr = cnt[7:0];
    wire signed [31:0] bp_bias = 32'sd0;
    wire signed [31:0] bp_m    = m_data;

    wire        act_we4    = (state == S_LOADQ);
    wire        act_we     = 1'b0;
    wire [31:0] act_data32 = q_rd_data4;

    reg  engine_start;
    wire engine_done;

    kwt_gemm_engine #(
        .IN_DIM(IN_DIM), .OUT_DIM(OUT_DIM), .TOKENS(TOKENS),
        .WB(8), .OUT_BITS(16),
        .AW_ACT(13), .AW_WGT(14), .AW_BP(8), .AW_OUT(13)
    ) u_engine (
        .clk(clk), .rst_n(rst_n), .start(engine_start),
        .act_we(act_we), .act_addr(act_addr), .act_data(act_data),
        .act_we4(act_we4), .act_data32(act_data32),
        .wgt_we(wgt_we), .wgt_addr(wgt_addr), .wgt_data(wgt_data),
        .wgt_we16(1'b0), .wgt_data16(64'd0), .wgt_we4(wgt_we4), .wgt_data_w4(wgt_word4),
        .bp_we(bp_we), .bp_addr(bp_addr), .bp_bias(bp_bias), .bp_m(bp_m),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(engine_done), .cycle_count()
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            cnt         <= 14'd0;
            tc          <= 8'd0;
            ti          <= 7'd0;
            wgt_we      <= 1'b0;
            q_rd_addr   <= 13'd0;
            engine_start <= 1'b0;
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
                        state       <= S_LOADQ;
                        q_rd_addr   <= 13'd0;
                    end
                end

                // stream Q into the activation buffer, four bytes per cycle
                S_LOADQ: begin
                    if (cnt == TOTAL_ACT-4) begin
                        cnt        <= 14'd0;
                        wgt_we     <= 1'b0;
                        state      <= S_LOADK;
                    end else begin
                        cnt       <= cnt + 14'd4;
                        q_rd_addr <= q_rd_addr + 13'd4;
                    end
                end

                // K is streamed straight into the engine weight buffer.
                // Row c of the weight matrix is token c of K, so the address
                // mapping is the identity; channels 99 (padding) get zeros.
                S_LOADK: begin
                    if (cnt == TOTAL_WGT-4) begin
                        cnt   <= 14'd0;
                        state <= S_LOADM;
                    end else begin
                        cnt <= cnt + 14'd4;
                    end
                end

                // same multiplier on every channel, zero bias; the last
                // weight write lands in this state's first cycle
                S_LOADM: begin
                    wgt_we <= 1'b0;
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
