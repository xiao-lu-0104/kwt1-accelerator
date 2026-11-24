`timescale 1ns / 1ps
// Row-wise LayerNorm: int16 in (scale s_r) -> int8 out (scale s_ln).
//
//   mean = (sum + N/2) >> 6
//   var  = sum((x-mean)^2) >> 6
//   inv  = 1/sqrt(var + eps)      LUT init + three Newton iterations (Q16.16)
//   y_q8 = (d * inv) >> 8
//   out  = sat8(((y_q8 * gamma_q) >> 16) + beta_q)
//
// gamma_q = gamma * s_r * 256 / s_ln, beta_q = beta / s_ln  (tools/calibrate.py)
module kwt_layernorm #(
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
    localparam S_ODRAIN = 4'd8;
    localparam S_SDRAIN = 4'd9;
    localparam S_VDRAIN = 4'd10;

    reg [3:0]  state;
    reg [6:0]  row;
    reg [6:0]  col;
    reg [1:0]  iter;
    reg signed [31:0] sum_r;
    reg signed [31:0] mean_r;
    reg signed [31:0] var_r;
    reg signed [31:0] inv_r;
    // Newton intermediates; each dependent multiply uses a shared pipeline.
    reg [2:0]         newt_ph;
    reg signed [63:0] y0sq_r, vy_r, t3_r;

    // four lanes per cycle over the row
    localparam DB=(N==64)?17:32;
    wire signed [15:0] x0 = x_buf[row*N + col];
    wire signed [15:0] x1 = x_buf[row*N + col + 7'd1];
    wire signed [15:0] x2 = x_buf[row*N + col + 7'd2];
    wire signed [15:0] x3 = x_buf[row*N + col + 7'd3];

    // Registered row statistics: SRAM read -> difference -> square ->
    // pair sums -> group sum -> accumulator. Keep variance modulo int32.
    reg signed [15:0] rx[0:3];
    reg signed [DB-1:0] vd[0:3];
    reg [31:0] vsq[0:3],vp0,vp1,vtotal;
    reg signed [16:0] sp0,sp1;
    reg signed [17:0] stotal;
    reg [2:0] sum_v,sum_l;
    reg [4:0] var_v,var_l;
    integer stat_i;
    always @(posedge clk) begin
        rx[0]<=x0;rx[1]<=x1;rx[2]<=x2;rx[3]<=x3;
        sp0<=$signed({rx[0][15],rx[0]})+$signed({rx[1][15],rx[1]});
        sp1<=$signed({rx[2][15],rx[2]})+$signed({rx[3][15],rx[3]});
        stotal<=$signed({sp0[16],sp0})+$signed({sp1[16],sp1});
        for(stat_i=0;stat_i<4;stat_i=stat_i+1) begin
            vd[stat_i]<=$signed(rx[stat_i])-$signed(mean_r);
            vsq[stat_i]<=vd[stat_i]*vd[stat_i];
        end
        vp0<=vsq[0]+vsq[1];vp1<=vsq[2]+vsq[3];
        vtotal<=vp0+vp1;
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin sum_v<=0;sum_l<=0;var_v<=0;var_l<=0;end
        else begin
            sum_v<={sum_v[1:0],state==S_SUM};sum_l<={sum_l[1:0],col>=N-4};
            var_v<={var_v[3:0],state==S_VAR};var_l<={var_l[3:0],col>=N-4};
        end
    end

    // Newton: y = y*(3 - v*y^2)/2, Q16.16
    // y0sq=inv^2>>16; vy=var*y0sq; t3=3-vy; inv=inv*t3>>17.
    wire signed [63:0] t3   = 64'sd196608 - vy_r;
    wire signed [31:0] newt_a=(newt_ph==2)?var_r:inv_r;
    wire signed [63:0] newt_b=(newt_ph==0)?{{32{inv_r[31]}},inv_r}:
                                         (newt_ph==2)?y0sq_r:t3_r;
    wire newt_issue=(state==S_NEWT)&&(newt_ph==0||newt_ph==2||newt_ph==5);
    wire newt_valid;
    wire signed [63:0] newt_product;
    wire signed [63:0] y1=newt_product>>>17;
    kwt_mul_pipe #(.A_BITS(32),.B_BITS(64)) u_newt_mul(
        .clk(clk),.rst_n(rst_n),.valid_in(newt_issue),.a(newt_a),.b(newt_b),
        .valid_out(newt_valid),.product(newt_product));

    // For N=64, rounded mean of 64 int16 values is int16. Hence d is
    // exactly signed 17 bits; d*inv is 49 bits, (d*inv)>>8 is 41 bits,
    // and multiplying that by int16 gamma fits 57 bits without overflow.
    // Other N retain the full original 32-bit difference/64-bit semantics.
    localparam YB=DB+32-8;
    reg signed [15:0] ox0,og0,ob0,og1,ob1;
    reg signed [DB-1:0] od1;
    reg [AW-1:0] oa0,oa1;
    reg ol0,ol1,ov0,ov1;
    wire signed [DB-1:0] ox_ext=ox0, mean_ext=mean_r;
    reg signed [15:0] ng[0:5],nb[0:5],gb[0:5];
    reg [AW-1:0] na[0:5],ga[0:5];
    reg nl[0:5],gl[0:5];
    wire nv,gv;
    wire signed [63:0] np,gp;
    wire signed [YB-1:0] normalized=$signed(np)>>>8;
    kwt_mul_pipe #(.A_BITS(DB),.B_BITS(32)) u_out_norm (
        .clk(clk),.rst_n(rst_n),.valid_in(ov1),.a(od1),.b(inv_r),
        .valid_out(nv),.product(np));
    kwt_mul_pipe #(.A_BITS(YB),.B_BITS(16)) u_out_gamma (
        .clk(clk),.rst_n(rst_n),.valid_in(nv),.a(normalized),.b(ng[5]),
        .valid_out(gv),.product(gp));
    localparam GB=(N==64)?57:64;
    localparam SB=(N==64)?42:64;
    wire signed [GB-1:0] gamma_product=gp[GB-1:0];
    wire signed [SB-1:0] gamma_scaled=$signed(gamma_product)>>>16;
    reg signed [SB-1:0] out_sum;
    reg [AW-1:0] sum_addr;
    reg sum_last,sum_valid;
    integer op;
    always @(posedge clk) begin
        ox0<=x0; og0<=gamma_q[col]; ob0<=beta_q[col];
        oa0<=row*N+col; ol0<=(col==N-1);
        od1<=ox_ext-mean_ext; og1<=og0; ob1<=ob0; oa1<=oa0; ol1<=ol0;
        ng[0]<=og1; nb[0]<=ob1; na[0]<=oa1; nl[0]<=ol1;
        gb[0]<=nb[5]; ga[0]<=na[5]; gl[0]<=nl[5];
        for(op=1;op<6;op=op+1) begin
            ng[op]<=ng[op-1]; nb[op]<=nb[op-1]; na[op]<=na[op-1]; nl[op]<=nl[op-1];
            gb[op]<=gb[op-1]; ga[op]<=ga[op-1]; gl[op]<=gl[op-1];
        end
        out_sum<=gamma_scaled+$signed(gb[5]);
        sum_addr<=ga[5]; sum_last<=gl[5];
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin ov0<=0; ov1<=0; sum_valid<=0; end
        else begin ov0<=(state==S_OUT); ov1<=ov0; sum_valid<=gv; end
    end

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
            newt_ph<=0;
        end else begin
            out_we      <= 1'b0;
            if(sum_valid) begin
                out_we<=1;
                out_addr<=sum_addr;
                out_data<=(out_sum>127)?8'sd127:(out_sum< -127)?-8'sd127:out_sum[7:0];
            end
            cycle_count <= cycle_count + 32'd1;
            if(sum_v[2]) sum_r<=sum_r+stotal;
            if(var_v[4]) var_r<=var_r+vtotal;
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
                    if (col >= N-4) begin col <= 7'd0; state <= S_SDRAIN; end
                    else col <= col + 7'd4;
                end

                S_SDRAIN: if(sum_v[2]&&sum_l[2]) state<=S_MEAN;

                S_MEAN: begin
                    mean_r <= (sum_r + (N/2)) >>> 6;
                    var_r  <= 32'sd0;
                    col    <= 7'd0;
                    state  <= S_VAR;
                end

                S_VAR: begin
                    if (col >= N-4) begin
                        col   <= 7'd0;
                        state <= S_VDRAIN;
                    end else begin
                        col <= col + 7'd4;
                    end
                end

                S_VDRAIN: if(var_v[4]&&var_l[4]) state<=S_RSQ;

                S_RSQ: begin
                    inv_r <= inv0;
                    var_r <= var_new;
                    state <= S_NEWT;
                    iter  <= 2'd0;
                    newt_ph <= 2'd0;
                end

                S_NEWT: begin
                    // Shared pipelined multiplier; preserve low64 truncation
                    // before each arithmetic shift and the original clamp.
                    case (newt_ph)
                        0: newt_ph<=1;
                        1: if(newt_valid) begin y0sq_r<=newt_product>>>16;newt_ph<=2;end
                        2: newt_ph<=3;
                        3: if(newt_valid) begin vy_r<=newt_product;newt_ph<=4;end
                        4: begin t3_r<=t3;newt_ph<=5;end
                        5: newt_ph<=6;
                        6: if(newt_valid) begin
                            inv_r   <= (y1 > 64'sd0) ? y1[31:0] : 32'sd1;
                            newt_ph <= 2'd0;
                            if (iter == 2'd2) begin
                                col   <= 7'd0;
                                state <= S_OUT;
                            end else begin
                                iter <= iter + 2'd1;
                            end
                        end
                        default: newt_ph<=0;
                    endcase
                end

                S_OUT: begin
                    if (col == N-1) begin
                        col <= 7'd0;
                        state<=S_ODRAIN;
                    end else begin
                        col <= col + 7'd1;
                    end
                end

                S_ODRAIN: if(sum_valid&&sum_last) begin
                        if (row == ROWS-1) begin
                            state <= S_DONE;
                        end else begin
                            row   <= row + 7'd1;
                            sum_r <= 32'sd0;
                            state <= S_SUM;
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
