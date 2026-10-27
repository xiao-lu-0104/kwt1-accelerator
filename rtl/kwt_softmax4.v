`timescale 1ns / 1ps
// Four elements/cycle within one row. Serial score input, masked quad output.
// Exact LUT, floor reciprocal and round-to-nearest probability contract.
// Read, comparison, LUT, reduction and multiply stages are all registered.
module kwt_softmax4 #(parameter N=99, parameter AW=7)(
    input wire clk, input wire rst_n, input wire start,
    input wire s_we, input wire [AW-1:0] s_addr,
    input wire signed [15:0] s_data,
    output reg out_we, output reg [AW-1:0] out_addr,
    output reg [31:0] out_data, output reg [3:0] out_mask,
    output reg done, output reg [31:0] cycle_count
);
    localparam G=(N+3)/4;
    localparam IDLE=0,MAX=1,MAXD=2,EXP=3,EXPD=4,INV=5,DIV=6,
               MUL=7,MULD=8,DONE=9;
    reg [3:0] state;
    reg [AW-1:0] idx;
    reg signed [15:0] score[0:3][0:G-1];
    reg [14:0] exps[0:3][0:G-1];
    always @(posedge clk) if(s_we) score[s_addr[1:0]][s_addr>>2]<=s_data;
    wire signed [15:0] s[0:3];
    genvar g;
    generate for(g=0;g<4;g=g+1) begin: g_lane
        assign s[g]=(idx+g<N)?score[g][idx>>2]:-16'sd32768;
    end endgenerate

    reg signed [15:0] max_r,m_in[0:3],m_pair0,m_pair1,m_group;
    reg [2:0] mv,ml;
    reg [31:0] sum_r;
    reg [11:0] inv_r; // sum >= 32767, so floor((127<<20)/sum) <= 4064.
    reg [26:0] div_q;
    reg [31:0] div_rem;
    reg [4:0] div_left;
    wire [32:0] trial={div_rem,div_q[26]};
    wire take=(trial>={1'b0,sum_r});
    wire [32:0] sub=trial-{1'b0,sum_r};
    wire [26:0] qnext={div_q[25:0],take};

    reg signed [15:0] e_in[0:3];
    reg [7:0] lut_idx[0:3];
    wire [15:0] lut_val[0:3];
    reg [14:0] e_value[0:3];
    reg [4:0] ev,el;
    reg [AW-1:0] eb[0:4];
    reg [16:0] e_pair0,e_pair1;
    reg [17:0] e_total;
    generate for(g=0;g<4;g=g+1) begin: g_exp
        wire signed [16:0] delta=$signed({max_r[15],max_r})-
                                         $signed({e_in[g][15],e_in[g]});
        wire [15:0] du=delta[16]?16'd0:delta[15:0];
        always @(posedge clk) begin
            e_in[g]<=s[g];
            lut_idx[g]<=(du>4080)?8'd255:du[11:4];
            e_value[g]<=(eb[1]+g<N)?lut_val[g][14:0]:15'd0;
            if(ev[2]&&eb[2]+g<N) exps[g][eb[2]>>2]<=e_value[g];
        end
        kwt_exp_lut u_lut(.idx(lut_idx[g]),.val(lut_val[g]));
    end endgenerate

    reg [14:0] p_in[0:3];
    reg [26:0] p_product[0:3];
    reg [27:0] p_round[0:3];
    reg [2:0] pv,pl;
    reg [AW-1:0] pb[0:2];
    generate for(g=0;g<4;g=g+1) begin: g_prob
        always @(posedge clk) begin
            p_in[g]<=(idx+g<N)?exps[g][idx>>2]:15'd0;
            p_product[g]<=p_in[g]*inv_r;
            p_round[g]<={1'b0,p_product[g]}+28'd524288;
        end
    end endgenerate

    integer j;
    always @(posedge clk) begin
        for(j=0;j<4;j=j+1) m_in[j]<=s[j];
        m_pair0<=($signed(m_in[0])>$signed(m_in[1]))?m_in[0]:m_in[1];
        m_pair1<=($signed(m_in[2])>$signed(m_in[3]))?m_in[2]:m_in[3];
        m_group<=($signed(m_pair0)>$signed(m_pair1))?m_pair0:m_pair1;
        eb[0]<=idx;
        for(j=1;j<5;j=j+1) eb[j]<=eb[j-1];
        e_pair0<={2'd0,e_value[0]}+{2'd0,e_value[1]};
        e_pair1<={2'd0,e_value[2]}+{2'd0,e_value[3]};
        e_total<={1'b0,e_pair0}+{1'b0,e_pair1};
        pb[0]<=idx; pb[1]<=pb[0]; pb[2]<=pb[1];
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            mv<=0;ml<=0;ev<=0;el<=0;pv<=0;pl<=0;
        end else begin
            mv<={mv[1:0],state==MAX}; ml<={ml[1:0],idx+4>=N};
            ev<={ev[3:0],state==EXP}; el<={el[3:0],idx+4>=N};
            pv<={pv[1:0],state==MUL}; pl<={pl[1:0],idx+4>=N};
        end
    end

    integer o;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;idx<=0;max_r<=-16'sd32768;
            sum_r<=0;inv_r<=0;div_q<=0;div_rem<=0;div_left<=0;
            out_we<=0;out_addr<=0;out_data<=0;out_mask<=0;
            done<=0;cycle_count<=0;
        end else begin
            out_we<=0;out_mask<=0;cycle_count<=cycle_count+1;
            if(mv[2]&&$signed(m_group)>$signed(max_r)) max_r<=m_group;
            if(ev[4]) sum_r<=sum_r+{14'd0,e_total};
            if(pv[2]) begin
                out_we<=1;out_addr<=pb[2];
                for(o=0;o<4;o=o+1) begin
                    out_mask[o]<=(pb[2]+o<N);
                    out_data[o*8 +: 8]<=(p_round[o][27:20]>127)?8'd127:p_round[o][27:20];
                end
            end
            case(state)
                IDLE: begin
                    done<=0;idx<=0;
                    if(start) begin
                        max_r<=-16'sd32768;sum_r<=0;cycle_count<=0;state<=MAX;
                    end
                end
                MAX: if(idx+4>=N) begin idx<=0;state<=MAXD;end else idx<=idx+4;
                MAXD: if(mv[2]&&ml[2]) state<=EXP;
                EXP: if(idx+4>=N) begin idx<=0;state<=EXPD;end else idx<=idx+4;
                EXPD: if(ev[4]&&el[4]) state<=INV;
                INV: begin
                    if(sum_r==0) begin inv_r<=0;state<=MUL;end
                    else begin div_q<=27'd133169152;div_rem<=0;div_left<=26;state<=DIV;end
                end
                DIV: begin
                    div_rem<=take?sub[31:0]:trial[31:0];div_q<=qnext;
                    if(div_left==0) begin inv_r<=qnext[11:0];state<=MUL;end
                    else div_left<=div_left-1'b1;
                end
                MUL: if(idx+4>=N) begin idx<=0;state<=MULD;end else idx<=idx+4;
                MULD: if(pv[2]&&pl[2]) state<=DONE;
                DONE: begin done<=1;if(!start) state<=IDLE;end
                default: state<=IDLE;
            endcase
        end
    end
    // synthesis translate_off
    initial if(N<1||N>128||AW<3) $fatal(1,"unsupported parallel softmax shape");
    always @(posedge clk) if(rst_n&&state==DIV&&div_left==0&&qnext[26:12]!=0)
        $fatal(1,"softmax reciprocal bound violated");
    // synthesis translate_on
endmodule
