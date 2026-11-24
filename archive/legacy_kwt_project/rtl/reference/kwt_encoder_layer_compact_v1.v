`timescale 1ns / 1ps
// Compact PostNorm encoder: one shared 64-multiply datapath, synchronous
// 16-bit SRAM banks, row-local score/probability/FFN/LayerNorm intermediates.
//
//   x -> attention -> o
//   r1 = align(x, o) -> LN1 -> x1
//   h  = F1 * x1 + b1 -> GELU (s_hin -> s_h)
//   f  = F2 * h  + b2
//   r2 = align(x1, f) -> LN2 -> out
//
// Parameter ports (loaded before start):
//   p_wgt_sel / p_bp_sel: 0=Q 1=K 2=V 3=O 4=FFN1 5=FFN2
//   p_ln_sel: 0=LN1 1=LN2
module kwt_encoder_layer_compact_v1 #(
    parameter TOK = 99,
    parameter D   = 64,
    parameter FF  = 256
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,

    input  wire               x_we,
    input  wire [12:0]        x_addr,
    input  wire [7:0]         x_data,

    input  wire               p_wgt_we,
    input  wire [2:0]         p_wgt_sel,
    input  wire [13:0]        p_wgt_addr,
    input  wire [3:0]         p_wgt_data,
    input  wire               p_wgt_we16,
    input  wire [63:0]        p_wgt_data16,

    input  wire               p_bp_we,
    input  wire [2:0]         p_bp_sel,
    input  wire [7:0]         p_bp_addr,
    input  wire signed [31:0] p_bp_bias,
    input  wire signed [31:0] p_bp_m,

    input  wire               p_ln_we,
    input  wire               p_ln_sel,
    input  wire [5:0]         p_ln_addr,
    input  wire signed [15:0] p_ln_gamma,
    input  wire signed [15:0] p_ln_beta,
    input  wire [31:0]        p_ln_eps,

    input  wire signed [31:0] m_score,
    input  wire signed [31:0] m_ctx,
    input  wire signed [15:0] ma1,
    input  wire signed [15:0] mb1,
    input  wire signed [15:0] ma2,
    input  wire signed [15:0] mb2,

    output reg                out_we,
    output reg  [12:0]        out_addr,
    output reg  [7:0]         out_data,

    output reg                done,
    output reg  [31:0]        cycle_count
);

    localparam IDLE=0, XREAD=1, XCAP=2, MREAD=3, MGO=4, MWAIT=5,
               BREAD=6, QUANT=7, ADVANCE=8, SMSTART=9, SMWAIT=10,
               COPY=11, LNLOAD=12, LNSTART=13, LNWAIT=14, FINISH=15;
    localparam PK=0, PV=1, PQ=2, PS=3, PA=4, PO=5, PF1=6, PF2=7;
    reg [4:0] state;
    reg [2:0] phase;
    reg [6:0] token, group_idx;
    reg [3:0] segment;
    reg [1:0] lane;
    reg [8:0] col;
    reg norm2;
    reg start_d;
    reg [127:0] accum;
    // These are deliberately small row registers, never complete matrices.
    reg [7:0] vec[0:255], result[0:255];
    reg [7:0] xrow[0:63], ln1row[0:63], prob[0:98];
    reg signed [15:0] lng[0:1][0:63], lnb[0:1][0:63];
    reg [31:0] eps_r;
    always @(posedge clk) if(p_ln_we) begin
        lng[p_ln_sel][p_ln_addr]<=p_ln_gamma;
        lnb[p_ln_sel][p_ln_addr]<=p_ln_beta;
    end

    function [9:0] wbase(input [2:0] sel);
        case(sel)
            0:wbase=0; 1:wbase=64; 2:wbase=128;
            3:wbase=192; 4:wbase=256; default:wbase=512;
        endcase
    endfunction
    function [9:0] bbase(input [2:0] sel);
        case(sel)
            0:bbase=0; 1:bbase=64; 2:bbase=128;
            3:bbase=192; 4:bbase=256; default:bbase=512;
        endcase
    endfunction
    wire [2:0] linear_sel=(phase==PK)?1:(phase==PV)?2:(phase==PQ)?0:
                             (phase==PO)?3:(phase==PF1)?4:5;
    wire [4:0] segments=(phase==PF2)?16:(phase==PA)?8:4;
    wire [6:0] groups=(phase==PF1)?64:(phase==PS)?25:16;
    wire [8:0] channel={group_idx,2'b00}+lane;

    // Weight storage: [output group][16-input segment][output lane][nibble].
    wire [7:0] load_c=(p_wgt_sel==5)?p_wgt_addr[13:8]:p_wgt_addr[13:6];
    wire [3:0] load_seg=(p_wgt_sel==5)?p_wgt_addr[7:4]:{2'b0,p_wgt_addr[5:4]};
    wire [9:0] wwaddr=wbase(p_wgt_sel)+
                   ((p_wgt_sel==5)?({2'b0,load_c[7:2]}*16):({2'b0,load_c[7:2]}*4))+load_seg;
    wire [9:0] wraddr=wbase(linear_sel)+group_idx*segments+segment;
    reg [255:0] wwdata;
    reg [63:0] wwmask;
    integer j, k;
    always @* begin
        wwdata=0; wwmask=0;
        if(p_wgt_we16) begin
            wwdata[load_c[1:0]*64 +: 64]=p_wgt_data16;
            wwmask[load_c[1:0]*16 +: 16]=16'hffff;
        end else if(p_wgt_we) begin
            wwdata[(load_c[1:0]*16+p_wgt_addr[3:0])*4 +: 4]=p_wgt_data;
            wwmask[load_c[1:0]*16+p_wgt_addr[3:0]]=1;
        end
    end
    wire [255:0] wq;
    kwt_packed_sram #(.DW(256),.DEPTH(1024)) u_weights (
        .clk(clk),.rst_n(rst_n),.wr(p_wgt_we16|p_wgt_we),.wa(wwaddr),
        .wd(wwdata),.mask(wwmask),.ra(wraddr),.rd(wq));

    // One bias/multiplier read and one requantiser, reused by all four lanes.
    wire [63:0] bq;
    wire [9:0] bpwa=bbase(p_bp_sel)+p_bp_addr;
    wire [9:0] bpra=bbase(linear_sel)+channel;
    kwt_packed_sram #(.DW(64),.DEPTH(1024)) u_params (
        .clk(clk),.rst_n(rst_n),.wr(p_bp_we),.wa(bpwa),
        .wd({p_bp_m,p_bp_bias}),.mask(16'hffff),.ra(bpra),.rd(bq));

    wire [127:0] xq;
    reg [127:0] xwd;
    reg [31:0] xwm;
    always @* begin
        xwd=0; xwm=0;
        xwd[x_addr[3:0]*8 +: 8]=x_data;
        xwm[x_addr[3:0]*2 +: 2]=2'b11;
    end
    wire [9:0] xwa={1'b0,x_addr[12:4]};
    wire [9:0] xra=token*4+col[5:4];
    kwt_packed_sram #(.DW(128),.DEPTH(1024)) u_x (
        .clk(clk),.rst_n(rst_n),.wr(x_we),.wa(xwa),.wd(xwd),.mask(xwm),
        .ra(xra),.rd(xq));

    function signed [15:0] requant(input signed [31:0] a,
                                  input signed [31:0] m, input wide_out);
        reg signed [63:0] product, shifted;
        reg signed [31:0] lim;
        begin
            product=a*m;
            shifted=(product+64'sd1073741824)>>>31;
            lim=wide_out?32767:127;
            if(shifted>lim) requant=lim;
            else if(shifted< -lim) requant=-lim;
            else requant=shifted[15:0];
        end
    endfunction
    wire signed [31:0] sum_bias=$signed(accum[lane*32 +: 32])+
                                       ((phase==PS||phase==PA)?32'sd0:$signed(bq[31:0]));
    wire signed [31:0] multiplier=(phase==PS)?m_score:(phase==PA)?m_ctx:$signed(bq[63:32]);
    wire signed [15:0] quant=requant(sum_bias,multiplier,phase==PS);
    wire signed [8:0] gelu_index=$signed(quant[7:0])+9'sd127;
    wire [7:0] gelu_idx=(gelu_index<0)?0:(gelu_index>254)?254:gelu_index[7:0];
    wire [7:0] gelu_q;
    kwt_gelu_lut u_gelu(.idx(gelu_idx),.val(gelu_q));

    // K is grouped by four tokens; V is transposed into four output channels.
    // Both use 32 parallel 16x128 macros: 8 KiB each, no multiport replication.
    wire kvwr=(state==QUANT)&&(phase==PK||phase==PV);
    wire [6:0] kwa=(token/4)*4+channel[5:4];
    wire [6:0] vwa=group_idx*8+token[6:4];
    wire [6:0] kra=group_idx*4+segment;
    wire [6:0] vra=group_idx*8+segment;
    reg [511:0] kwd,vwd;
    reg [127:0] kwm,vwm;
    always @* begin
        kwd=0; kwm=0; vwd=0; vwm=0;
        kwd[(token[1:0]*16+channel[3:0])*8 +: 8]=quant[7:0];
        kwm[(token[1:0]*16+channel[3:0])*2 +: 2]=2'b11;
        vwd[(lane*16+token[3:0])*8 +: 8]=quant[7:0];
        vwm[(lane*16+token[3:0])*2 +: 2]=2'b11;
    end
    wire [511:0] kq,vq;
    kwt_packed_sram #(.DW(512),.DEPTH(128)) u_k (
        .clk(clk),.rst_n(rst_n),.wr(kvwr&&phase==PK),.wa(kwa),
        .wd(kwd),.mask(kwm),.ra(kra),.rd(kq));
    kwt_packed_sram #(.DW(512),.DEPTH(128)) u_v (
        .clk(clk),.rst_n(rst_n),.wr(kvwr&&phase==PV),.wa(vwa),
        .wd(vwd),.mask(vwm),.ra(vra),.rd(vq));

    reg [127:0] mac_a;
    reg [511:0] mac_w;
    always @* begin
        mac_a=0; mac_w=0;
        for(j=0;j<16;j=j+1) begin
            if(phase==PA) begin
                if(segment*16+j<TOK) mac_a[j*8 +: 8]=prob[segment*16+j];
            end else if(phase==PS) mac_a[j*8 +: 8]=result[segment*16+j];
            else mac_a[j*8 +: 8]=vec[segment*16+j];
            for(k=0;k<4;k=k+1) begin
                if(phase==PS) begin
                    if(group_idx*4+k<TOK) mac_w[(k*16+j)*8 +: 8]=kq[(k*16+j)*8 +: 8];
                end else if(phase==PA) begin
                    if(segment*16+j<TOK) mac_w[(k*16+j)*8 +: 8]=vq[(k*16+j)*8 +: 8];
                end else mac_w[(k*16+j)*8 +: 8]=
                    {{4{wq[(k*16+j)*4+3]}},wq[(k*16+j)*4 +: 4]};
            end
        end
    end
    wire mac_issue=(state==MGO);
    wire mac_valid;
    wire [127:0] mac_out;
    kwt_mac16x4 u_mac(.clk(clk),.rst_n(rst_n),.valid_in(state==MGO),
        .a(mac_a),.w(mac_w),.acc_in(accum),.valid_out(mac_valid),.acc_out(mac_out));

    wire sm_we,sm_done;
    wire [6:0] sm_addr;
    wire [7:0] sm_data;
    kwt_softmax #(.N(TOK),.SERIAL_DIV(1)) u_sm(.clk(clk),.rst_n(rst_n),.start(state==SMSTART),
        .s_we(state==QUANT&&phase==PS&&channel<TOK),.s_addr(channel[6:0]),.s_data(quant),
        .out_we(sm_we),.out_addr(sm_addr),.out_data(sm_data),.done(sm_done),.cycle_count());

    wire signed [15:0] aligned;
    kwt_align_add u_align(.a(norm2?ln1row[col[5:0]]:xrow[col[5:0]]),
        .b(result[col[5:0]]),.ma(norm2?ma2:ma1),.mb(norm2?mb2:mb1),.y(aligned));
    wire ln_we,ln_done;
    wire [5:0] ln_addr;
    wire [7:0] ln_data;
    kwt_layernorm #(.ROWS(1),.AW(6)) u_ln (.clk(clk),.rst_n(rst_n),
        .start(state==LNSTART),.in_we(state==LNLOAD),.in_addr(col[5:0]),.in_data(aligned),
        .gp_we(state==LNLOAD),.gp_addr(col[5:0]),
        .gp_gamma(lng[norm2][col[5:0]]),.gp_beta(lnb[norm2][col[5:0]]),.eps_q(eps_r),
        .out_we(ln_we),.out_addr(ln_addr),.out_data(ln_data),.done(ln_done),.cycle_count());

    integer i;
    // Data registers are intentionally unreset. Keep them separate from the
    // async-reset controller so synthesis does not infer reset/hold muxes.
    always @(posedge clk) begin
        if(rst_n) begin
            if(sm_we) prob[sm_addr]<=sm_data;
            if(state==XCAP) begin
                for(i=0;i<16;i=i+1) begin
                    vec[col+i]<=xq[i*8 +: 8];
                    xrow[col+i]<=xq[i*8 +: 8];
                end
            end else if(ln_we&&state==LNWAIT&&!norm2) begin
                vec[ln_addr]<=ln_data;
                ln1row[ln_addr]<=ln_data;
            end else if(state==COPY) vec[col]<=result[col];
            if(state==QUANT&&phase!=PK&&phase!=PV&&phase!=PS)
                result[channel]<=(phase==PF1)?gelu_q:quant[7:0];
        end
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE; phase<=PK; token<=0; group_idx<=0; segment<=0;
            lane<=0; col<=0; norm2<=0; accum<=0; eps_r<=0; start_d<=0;
            done<=0; cycle_count<=0; out_we<=0; out_addr<=0; out_data<=0;
        end else begin
            out_we<=0;
            start_d<=start;
            if(state!=IDLE&&state!=FINISH) cycle_count<=cycle_count+1;
            if(ln_we&&state==LNWAIT) begin
                if(norm2) begin
                    out_we<=1; out_addr<=token*64+ln_addr; out_data<=ln_data;
                end
            end
            case(state)
                IDLE: begin
                    done<=0;
                    if(start) begin
                        cycle_count<=0; token<=0; col<=0; phase<=PK;
                        eps_r<=p_ln_eps; state<=XREAD;
                    end
                end
                XREAD: state<=XCAP;
                XCAP: begin
                    if(col==48) begin
                        col<=0; group_idx<=0; segment<=0; accum<=0; state<=MREAD;
                    end else begin col<=col+16; state<=XREAD; end
                end
                MREAD: state<=MGO;
                MGO: state<=MWAIT;
                MWAIT: if(mac_valid) begin
                    accum<=mac_out;
                    if(segment==segments-1) begin lane<=0; state<=BREAD; end
                    else begin segment<=segment+1; state<=MREAD; end
                end
                BREAD: state<=QUANT;
                QUANT: begin
                    if(lane==3) begin
                        lane<=0; segment<=0; accum<=0;
                        if(group_idx==groups-1) begin group_idx<=0; state<=ADVANCE; end
                        else begin group_idx<=group_idx+1; state<=MREAD; end
                    end else begin lane<=lane+1; state<=BREAD; end
                end
                ADVANCE: begin
                    col<=0;
                    case(phase)
                        PK: begin phase<=PV; state<=MREAD; end
                        PV: if(token==TOK-1) begin
                            token<=0; phase<=PQ; state<=XREAD;
                        end else begin token<=token+1; phase<=PK; state<=XREAD; end
                        PQ: begin phase<=PS; state<=MREAD; end
                        PS: state<=SMSTART;
                        PA: begin phase<=PO; state<=COPY; end
                        PO: begin norm2<=0; state<=LNLOAD; end
                        PF1: begin phase<=PF2; state<=COPY; end
                        PF2: begin norm2<=1; state<=LNLOAD; end
                    endcase
                end
                SMSTART: state<=SMWAIT;
                SMWAIT: if(sm_done) begin phase<=PA; state<=MREAD; end
                COPY: begin
                    if(col==((phase==PF2)?255:63)) begin col<=0; state<=MREAD; end
                    else col<=col+1;
                end
                LNLOAD: if(col==63) begin col<=0; state<=LNSTART; end
                        else col<=col+1;
                LNSTART: state<=LNWAIT;
                LNWAIT: if(ln_done) begin
                    if(!norm2) begin phase<=PF1; state<=MREAD; end
                    else if(token==TOK-1) begin state<=FINISH; done<=1; end
                    else begin token<=token+1; phase<=PQ; col<=0; state<=XREAD; end
                end
                FINISH: begin
                    // The twelve-layer scheduler sends a pulse while done is high.
                    if(start&&!start_d) begin
                        done<=0; cycle_count<=0; token<=0; col<=0; phase<=PK;
                        eps_r<=p_ln_eps; state<=XREAD;
                    end
                end
                default: state<=IDLE;
            endcase
        end
    end
    // synthesis translate_off
    initial begin
        if(TOK!=99||D!=64||FF!=256) $fatal(1,"compact encoder supports KWT-1 99x64x256 only");
    end
    always @(posedge clk) if(rst_n && p_wgt_we16 && p_wgt_addr[3:0]!=0)
        $fatal(1,"wide parameter writes must be 16-element aligned");
    // synthesis translate_on
endmodule

