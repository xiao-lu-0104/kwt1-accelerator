`timescale 1ns / 1ps
// Q/K/V projection stage of the attention block.
//
// Three independent GEMM engines (IN=64, OUT=64, int4 weights) run in
// sequence. The host loads x three times (or the same x buffer feeds all
// three, see the SoC wiring) and collects each result stream.
//
// Each engine exposes its own load ports so the parameter loader can fill
// them directly; this keeps the control FSM trivial.
module kwt_attn_qkv (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    // ---- Q engine load ports ----
    input  wire               q_act_we,
    input  wire [12:0]        q_act_addr,
    input  wire [7:0]         q_act_data,
    input  wire               q_act_we4,
    input  wire [31:0]        q_act_data32,
    input  wire               q_wgt_we,
    input  wire [13:0]        q_wgt_addr,
    input  wire [3:0]         q_wgt_data,
    input  wire               q_wgt_we16,
    input  wire [63:0]        q_wgt_data16,
    input  wire               q_bp_we,
    input  wire [7:0]         q_bp_addr,
    input  wire signed [31:0] q_bp_bias,
    input  wire signed [31:0] q_bp_m,
    output wire               q_out_we,
    output wire [12:0]        q_out_addr,
    output wire [31:0]        q_out_data,

    // ---- K engine load ports ----
    input  wire               k_act_we,
    input  wire [12:0]        k_act_addr,
    input  wire [7:0]         k_act_data,
    input  wire               k_act_we4,
    input  wire [31:0]        k_act_data32,
    input  wire               k_wgt_we,
    input  wire [13:0]        k_wgt_addr,
    input  wire [3:0]         k_wgt_data,
    input  wire               k_wgt_we16,
    input  wire [63:0]        k_wgt_data16,
    input  wire               k_bp_we,
    input  wire [7:0]         k_bp_addr,
    input  wire signed [31:0] k_bp_bias,
    input  wire signed [31:0] k_bp_m,
    output wire               k_out_we,
    output wire [12:0]        k_out_addr,
    output wire [31:0]        k_out_data,

    // ---- V engine load ports ----
    input  wire               v_act_we,
    input  wire [12:0]        v_act_addr,
    input  wire [7:0]         v_act_data,
    input  wire               v_act_we4,
    input  wire [31:0]        v_act_data32,
    input  wire               v_wgt_we,
    input  wire [13:0]        v_wgt_addr,
    input  wire [3:0]         v_wgt_data,
    input  wire               v_wgt_we16,
    input  wire [63:0]        v_wgt_data16,
    input  wire               v_bp_we,
    input  wire [7:0]         v_bp_addr,
    input  wire signed [31:0] v_bp_bias,
    input  wire signed [31:0] v_bp_m,
    output wire               v_out_we,
    output wire [12:0]        v_out_addr,
    output wire [31:0]        v_out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam IN_DIM  = 64;
    localparam OUT_DIM = 64;
    localparam TOKENS  = 99;

    wire q_done, k_done, v_done;
    reg  q_start, k_start, v_start;

    kwt_gemm_engine #(.IN_DIM(IN_DIM), .OUT_DIM(OUT_DIM), .TOKENS(TOKENS), .WB(4),
                      .AW_ACT(13), .AW_WGT(14), .AW_BP(8), .AW_OUT(13)) u_q (
        .clk(clk), .rst_n(rst_n), .start(q_start),
        .act_we(q_act_we), .act_addr(q_act_addr), .act_data(q_act_data),
        .act_we4(q_act_we4), .act_data32(q_act_data32),
        .wgt_we(q_wgt_we), .wgt_addr(q_wgt_addr), .wgt_data(q_wgt_data),
        .wgt_we16(q_wgt_we16), .wgt_data16(q_wgt_data16), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(q_bp_we), .bp_addr(q_bp_addr), .bp_bias(q_bp_bias), .bp_m(q_bp_m),
        .out_we(q_out_we), .out_addr(q_out_addr), .out_data(q_out_data),
        .done(q_done), .cycle_count()
    );

    kwt_gemm_engine #(.IN_DIM(IN_DIM), .OUT_DIM(OUT_DIM), .TOKENS(TOKENS), .WB(4),
                      .AW_ACT(13), .AW_WGT(14), .AW_BP(8), .AW_OUT(13)) u_k (
        .clk(clk), .rst_n(rst_n), .start(k_start),
        .act_we(k_act_we), .act_addr(k_act_addr), .act_data(k_act_data),
        .act_we4(k_act_we4), .act_data32(k_act_data32),
        .wgt_we(k_wgt_we), .wgt_addr(k_wgt_addr), .wgt_data(k_wgt_data),
        .wgt_we16(k_wgt_we16), .wgt_data16(k_wgt_data16), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(k_bp_we), .bp_addr(k_bp_addr), .bp_bias(k_bp_bias), .bp_m(k_bp_m),
        .out_we(k_out_we), .out_addr(k_out_addr), .out_data(k_out_data),
        .done(k_done), .cycle_count()
    );

    kwt_gemm_engine #(.IN_DIM(IN_DIM), .OUT_DIM(OUT_DIM), .TOKENS(TOKENS), .WB(4),
                      .AW_ACT(13), .AW_WGT(14), .AW_BP(8), .AW_OUT(13)) u_v (
        .clk(clk), .rst_n(rst_n), .start(v_start),
        .act_we(v_act_we), .act_addr(v_act_addr), .act_data(v_act_data),
        .act_we4(v_act_we4), .act_data32(v_act_data32),
        .wgt_we(v_wgt_we), .wgt_addr(v_wgt_addr), .wgt_data(v_wgt_data),
        .wgt_we16(v_wgt_we16), .wgt_data16(v_wgt_data16), .wgt_we4(1'b0), .wgt_data_w4(32'd0),
        .bp_we(v_bp_we), .bp_addr(v_bp_addr), .bp_bias(v_bp_bias), .bp_m(v_bp_m),
        .out_we(v_out_we), .out_addr(v_out_addr), .out_data(v_out_data),
        .done(v_done), .cycle_count()
    );

    localparam S_IDLE = 3'd0;
    localparam S_Q    = 3'd1;
    localparam S_K    = 3'd2;
    localparam S_V    = 3'd3;
    localparam S_DONE = 3'd4;

    reg [2:0] state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            q_start     <= 1'b0;
            k_start     <= 1'b0;
            v_start     <= 1'b0;
            done        <= 1'b0;
            cycle_count <= 32'd0;
        end else begin
            cycle_count <= cycle_count + 32'd1;
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    if (start) begin
                        // all three projections share the same activation stream,
                        // so they can run concurrently
                        q_start     <= 1'b1;
                        k_start     <= 1'b1;
                        v_start     <= 1'b1;
                        cycle_count <= 32'd0;
                        state       <= S_Q;
                    end
                end

                S_Q: begin
                    q_start <= 1'b0;
                    k_start <= 1'b0;
                    v_start <= 1'b0;
                    if (q_done && k_done && v_done) state <= S_DONE;
                end

                S_K: begin
                    if (q_done && k_done && v_done) state <= S_DONE;
                end

                S_V: begin
                    if (q_done && k_done && v_done) state <= S_DONE;
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
