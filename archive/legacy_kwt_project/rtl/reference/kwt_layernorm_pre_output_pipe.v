`timescale 1ns / 1ps
// Row-wise LayerNorm: int16 in (scale s_r) -> int8 out (scale s_ln).
//
//   mean = (sum + N/2) >> 6
//   var  = sum((x-mean)^2) >> 6
//   inv  = 1/sqrt(var + eps)      LUT init + two Newton iterations (Q16.16)
//   y_q8 = (d * inv) >> 8
//   out  = sat8(((y_q8 * gamma_q) >> 16) + beta_q)
//
// gamma_q = gamma * s_r * 256 / s_ln, beta_q = beta / s_ln  (tools/calibrate.py)
module kwt_layernorm_pre_output_pipe #(
    parameter N  = 64,
    parameter ROWS = 99,
    parameter AW = 13
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    input  wire               in_we,
    input  wire [AW-1:0]      in_addr,
    input  wire signed [15:0] in_data,

    input  wire               gp_we,
    input  wire [5:0]         gp_addr,
    input  wire signed [15:0] gp_gamma,
    input  wire signed [15:0] gp_beta,
    input  wire [31:0]        eps_q,

    output reg                out_we,
    output reg  [AW-1:0]      out_addr,
    output reg  signed [7:0]  out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    reg signed [15:0] x_buf  [0:ROWS*N-1];
    reg signed [15:0] gamma_q[0:N-1];
    reg signed [15:0] beta_q [0:N-1];

    always @(posedge clk) begin
        if (in_we) x_buf[in_addr] <= in_data;
        if (gp_we) begin
            gamma_q[gp_addr] <= gp_gamma;
            beta_q[gp_addr]  <= gp_beta;
        end
    end

    // variance finalisation and rsqrt lookup are combinational on the raw sum
    localparam S_IDLE = 4'd0;
    localparam S_SUM  = 4'd1;
    localparam S_MEAN = 4'd2;
    localparam S_VAR  = 4'd3;
    localparam S_RSQ  = 4'd4;
    localparam S_NEWT = 4'd5;
    localparam S_OUT  = 4'd6;
    localparam S_DONE = 4'd7;

    reg [3:0]  state;
    reg [6:0]  row;
    reg [6:0]  col;
    reg [1:0]  iter;
    reg signed [31:0] sum_r;
    reg signed [31:0] mean_r;
    reg signed [31:0] var_r;
    reg signed [31:0] inv_r;
    // Newton 迭代的流水寄存器：把原来一拍内串联的 3 个乘法拆成四级
    reg [1:0]         newt_ph;
    reg signed [63:0] y0sq_r, vy_r, t3_r;

    // four lanes per cycle over the row
    wire signed [15:0] x0 = x_buf[row*N + col];
    wire signed [15:0] x1 = x_buf[row*N + col + 7'd1];
    wire signed [15:0] x2 = x_buf[row*N + col + 7'd2];
    wire signed [15:0] x3 = x_buf[row*N + col + 7'd3];
    wire signed [31:0] d0 = x0 - mean_r;
    wire signed [31:0] d1 = x1 - mean_r;
    wire signed [31:0] d2 = x2 - mean_r;
    wire signed [31:0] d3 = x3 - mean_r;
    wire signed [31:0] d_cur = d0;   // output pass is still serially indexed
    wire signed [15:0] x_cur = x0;

    // Newton: y = y*(3 - v*y^2)/2, Q16.16
    // 四级流水：每拍只走一个乘法，避免 -20ns 的超长组合路径
    //   ph0: y0sq = inv^2      ph1: vy = var*y0sq
    //   ph2: t3 = 3 - vy       ph3: y1 = inv*t3
    wire signed [63:0] y0sq = (inv_r * inv_r) >>> 16;
    wire signed [63:0] vy   = var_r * y0sq_r;
    wire signed [63:0] t3   = 64'sd196608 - vy_r;
    wire signed [63:0] y1   = (inv_r * t3_r) >>> 17;

    // all intermediate products are kept at 64 bits: gamma_q reaches ~1e4
    // after the scale fix, so y_q8*gamma_q can exceed int32
    wire signed [63:0] d64   = d_cur;
    wire signed [63:0] inv64 = inv_r;
    wire signed [63:0] y_q8  = (d64 * inv64) >>> 8;
    wire signed [63:0] g64   = gamma_q[col];
    wire signed [63:0] b64   = beta_q[col];
    wire signed [63:0] gmul  = y_q8 * g64;
    wire signed [63:0] outv  = (gmul >>> 16) + b64;
    wire signed [7:0]  sat   = (outv > 64'sd127) ? 8'sd127 :
                               (outv < -64'sd127) ? -8'sd127 : outv[7:0];

    // variance finalisation and rsqrt lookup are combinational on the raw sum
    wire signed [31:0] var_new = (var_r >>> 6) + $signed(eps_q);
    wire [7:0] idx_rs = (var_new > 32'sd262143) ? 8'd255 : var_new[17:10];
    wire [31:0] inv0;
    kwt_rsqrt_lut u_rsqrt (.idx(idx_rs), .val(inv0));

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE; row <= 7'd0; col <= 7'd0; iter <= 2'd0;
            sum_r <= 0; mean_r <= 0; var_r <= 0; inv_r <= 0;
            out_we <= 1'b0; out_addr <= {AW{1'b0}}; out_data <= 8'sd0;
            done <= 1'b0; cycle_count <= 32'd0;
        end else begin
            out_we      <= 1'b0;
            cycle_count <= cycle_count + 32'd1;
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    row  <= 7'd0;
                    col  <= 7'd0;
                    if (start) begin
                        sum_r       <= 32'sd0;
                        cycle_count <= 32'd0;
                        state       <= S_SUM;
                    end
                end

                S_SUM: begin
                    sum_r <= sum_r + {{16{x0[15]}}, x0} + {{16{x1[15]}}, x1}
                                   + {{16{x2[15]}}, x2} + {{16{x3[15]}}, x3};
                    if (col >= N-4) begin col <= 7'd0; state <= S_MEAN; end
                    else col <= col + 7'd4;
                end

                S_MEAN: begin
                    mean_r <= (sum_r + (N/2)) >>> 6;
                    var_r  <= 32'sd0;
                    col    <= 7'd0;
                    state  <= S_VAR;
                end

                S_VAR: begin
                    var_r <= var_r + (d0*d0) + (d1*d1) + (d2*d2) + (d3*d3);
                    if (col >= N-4) begin
                        col   <= 7'd0;
                        state <= S_RSQ;
                    end else begin
                        col <= col + 7'd4;
                    end
                end

                S_RSQ: begin
                    inv_r <= inv0;
                    var_r <= var_new;
                    state <= S_NEWT;
                    iter  <= 2'd0;
                    newt_ph <= 2'd0;
                end

                S_NEWT: begin
                    // 四级流水，每级一个乘法；ph3 时才更新 inv_r 并决定是否继续迭代
                    case (newt_ph)
                        2'd0: begin y0sq_r  <= y0sq; newt_ph <= 2'd1; end
                        2'd1: begin vy_r    <= vy;   newt_ph <= 2'd2; end
                        2'd2: begin t3_r    <= t3;   newt_ph <= 2'd3; end
                        default: begin
                            inv_r   <= (y1 > 64'sd0) ? y1[31:0] : 32'sd1;
                            newt_ph <= 2'd0;
                            if (iter == 2'd2) begin
                                col   <= 7'd0;
                                state <= S_OUT;
                            end else begin
                                iter <= iter + 2'd1;
                            end
                        end
                    endcase
                end

                S_OUT: begin
                    out_we   <= 1'b1;
                    out_addr <= row*N + col;
                    out_data <= sat;
                    if (col == N-1) begin
                        col <= 7'd0;
                        if (row == ROWS-1) begin
                            state <= S_DONE;
                        end else begin
                            row   <= row + 7'd1;
                            sum_r <= 32'sd0;
                            state <= S_SUM;
                        end
                    end else begin
                        col <= col + 7'd1;
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
