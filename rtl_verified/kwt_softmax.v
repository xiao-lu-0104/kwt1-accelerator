`timescale 1ns / 1ps
// Row-wise softmax: N int16 scores -> N uint8 probabilities (0..127).
//
// Fixed-point contract (mirrors tools/fixed_softmax.py):
//   delta = max - score                 (>= 0)
//   idx   = min(255, delta >> 4)        (LUT step = 1/16 in real value)
//   e[i]  = EXP_LUT[idx]                (Q15, 0..32767)
//   total = sum(e)                      (>= 32767 because e[max] = LUT[0])
//   inv   = (127 << 20) / total
//   p[i]  = (e[i] * inv) >> 20          (<= 127 by construction)
module kwt_softmax #(
    parameter N  = 99,
    parameter AW = 7
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    input  wire               s_we,
    input  wire [AW-1:0]      s_addr,
    input  wire signed [15:0] s_data,

    output reg                out_we,
    output reg  [AW-1:0]      out_addr,
    output reg  [7:0]         out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    reg signed [15:0] score [0:N-1];
    reg [15:0]        e_val [0:N-1];

    always @(posedge clk) begin
        if (s_we) score[s_addr] <= s_data;
    end

    // ------------------------------------------------------------------
    // combinational datapath for the current index
    // ------------------------------------------------------------------
    reg [AW-1:0] idx;
    reg signed [15:0] max_r;
    reg [31:0] inv_r;

    wire signed [15:0] s_cur = score[idx];
    wire signed [31:0] delta = max_r - s_cur;          // 32-bit to avoid overflow
    wire [15:0] delta_u = (delta < 0) ? 16'd0 : delta[15:0];
    wire [7:0]  lut_idx = (delta_u > 16'd4080) ? 8'd255 : delta_u[11:4];

    wire [15:0] lut_val;
    kwt_exp_lut u_lut (.idx(lut_idx), .val(lut_val));

    wire [47:0] prod = e_val[idx] * inv_r;
    wire [47:0] p_rnd = prod + 48'd524288;      // + (1 << 19)
    wire [31:0] p_val = p_rnd >> 20;

    // ------------------------------------------------------------------
    // control
    // ------------------------------------------------------------------
    localparam S_IDLE = 3'd0;
    localparam S_MAX  = 3'd1;
    localparam S_EXP  = 3'd2;
    localparam S_INV  = 3'd3;
    localparam S_MUL  = 3'd4;
    localparam S_DONE = 3'd5;

    reg [2:0]  state;
    reg [31:0] sum_r;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            idx         <= {AW{1'b0}};
            max_r       <= -16'sd32768;
            sum_r       <= 32'd0;
            inv_r       <= 32'd0;
            out_we      <= 1'b0;
            out_addr    <= {AW{1'b0}};
            out_data    <= 8'd0;
            done        <= 1'b0;
            cycle_count <= 32'd0;
        end else begin
            out_we      <= 1'b0;
            cycle_count <= cycle_count + 32'd1;
            case (state)
                S_IDLE: begin
                    done  <= 1'b0;
                    idx   <= {AW{1'b0}};
                    if (start) begin
                        max_r       <= -16'sd32768;
                        sum_r       <= 32'd0;
                        cycle_count <= 32'd0;
                        state       <= S_MAX;
                    end
                end

                // pass 1: running max
                S_MAX: begin
                    if (s_cur > max_r) max_r <= s_cur;
                    if (idx == N-1) begin
                        idx   <= {AW{1'b0}};
                        state <= S_EXP;
                    end else begin
                        idx <= idx + 1'b1;
                    end
                end

                // pass 2: exp + sum
                S_EXP: begin
                    e_val[idx] <= lut_val;
                    sum_r      <= sum_r + {16'd0, lut_val};
                    if (idx == N-1) begin
                        idx   <= {AW{1'b0}};
                        state <= S_INV;
                    end else begin
                        idx <= idx + 1'b1;
                    end
                end

                // pass 3: reciprocal (single division)
                S_INV: begin
                    if (sum_r == 32'd0)
                        inv_r <= 32'd0;
                    else
                        inv_r <= (32'd127 << 20) / sum_r;
                    idx   <= {AW{1'b0}};
                    state <= S_MUL;
                end

                // pass 4: multiply and stream out
                S_MUL: begin
                    out_we   <= 1'b1;
                    out_addr <= idx;
                    out_data <= (p_val > 32'd127) ? 8'd127 : p_val[7:0];
                    if (idx == N-1) begin
                        state <= S_DONE;
                    end else begin
                        idx <= idx + 1'b1;
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
