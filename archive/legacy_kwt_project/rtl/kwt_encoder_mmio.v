`timescale 1ns / 1ps
// Encoder peripheral for the platform's ID-less AXI port. Normal requests are
// single 32-bit beats; unsupported bursts are drained/replied with errors.
// Input/output windows are sequential full-word transfers. See doc/MMIO接口.md.
module kwt_encoder_mmio #(
    parameter [31:0] BASE_ADDR=32'h40000000,
    parameter INPUT_BYTES=6336, parameter PARAM_WORDS=90768
)(
    input wire clk,rst_n,
    input wire axi_awvalid, output wire axi_awready, input wire [31:0] axi_awaddr,
    input wire [3:0] axi_awlen, input wire [2:0] axi_awsize,
    input wire [1:0] axi_awburst,axi_awlock,
    input wire axi_wvalid, output wire axi_wready, input wire [31:0] axi_wdata,
    input wire [3:0] axi_wstrb, input wire axi_wlast,
    output wire axi_bvalid, input wire axi_bready, output reg [1:0] axi_bresp,
    input wire axi_arvalid, output wire axi_arready, input wire [31:0] axi_araddr,
    input wire [3:0] axi_arlen, input wire [2:0] axi_arsize,
    input wire [1:0] axi_arburst,axi_arlock,
    output wire axi_rvalid, input wire axi_rready, output reg [31:0] axi_rdata,
    output reg [1:0] axi_rresp, output wire axi_rlast,
    output wire core_rst_n, output reg core_start,
    output wire x_we, output wire [12:0] x_addr, output wire [7:0] x_data,
    output wire param_valid, input wire param_ready, output wire [63:0] param_data,
    input wire [3:0] cur_layer,ld_sel, input wire [13:0] ld_addr,
    input wire core_out_we, input wire [12:0] core_out_addr, input wire [7:0] core_out_data,
    input wire core_done, input wire [31:0] core_cycles
);
    localparam WORDS=INPUT_BYTES/4;
    localparam W_IDLE=0,W_DATA=1,W_BYTES=2,W_RESP=3;
    localparam R_IDLE=0,R_LOW_WAIT=1,R_LOW_CAP=2,R_HIGH_WAIT=3,R_HIGH_CAP=4,R_RESP=5;
    reg [1:0] ws;
    reg [2:0] rs;
    reg [15:0] wa,ra;
    reg [3:0] wleft,rleft;
    reg wbad;
    reg [31:0] input_data;
    reg [1:0] input_lane;
    reg [15:0] input_words,output_bytes,read_words;
    reg [31:0] parameter_words,task_cycles,core_cycles_latched;
    reg busy,done,error,started,task_running,soft_reset,reading_output;
    reg [15:0] read_low;
    wire stream_ready,stream_empty;

    wire wfire=axi_wvalid&&axi_wready;
    wire ctrl_word=(wa==16'h0000);
    wire input_word=(wa>=16'h1000 && wa<16'h1000+INPUT_BYTES);
    wire parameter_word=(wa==16'h0030);
    wire can_start=!started&&!busy&&(input_words==WORDS)&&stream_empty;
    // A software reset may not invalidate an outstanding AXI read response.
    wire can_reset=(rs==R_IDLE)&&!axi_arvalid;
    wire valid_word=!wbad && (wleft==0) && axi_wlast && (wa[1:0]==0);
    wire enabled_param=valid_word&&parameter_word&&(axi_wstrb==4'hf)&&busy&&
                       (parameter_words<PARAM_WORDS);
    wire reset_request=wfire&&valid_word&&ctrl_word&&axi_wstrb[0]&&
                       (axi_wdata[1:0]==2)&&can_reset;
    wire start_request=wfire&&valid_word&&ctrl_word&&axi_wstrb[0]&&
                       (axi_wdata[1:0]==1)&&can_start;
    assign axi_awready=rst_n&&(ws==W_IDLE);
    assign axi_wready=rst_n&&(ws==W_DATA)&&(!enabled_param||stream_ready);
    assign axi_bvalid=(ws==W_RESP);
    assign axi_arready=rst_n&&(rs==R_IDLE);
    assign axi_rvalid=(rs==R_RESP);
    assign axi_rlast=(rleft==0);
    assign core_rst_n=rst_n&&!soft_reset;
    assign x_we=(ws==W_BYTES);
    assign x_addr=(wa-16'h1000)+input_lane;
    assign x_data=input_data>>(8*input_lane);

    kwt_param_stream u_stream(.clk(clk),.rst_n(core_rst_n),
        .s_valid(axi_wvalid&&(ws==W_DATA)&&enabled_param),.s_ready(stream_ready),.s_data(axi_wdata),
        .m_valid(param_valid),.m_ready(param_ready),.m_data(param_data),.empty(stream_empty));

    wire output_valid=core_out_we&&busy&&(output_bytes<INPUT_BYTES)&&
                      (core_out_addr==output_bytes)&&!reset_request;
    wire [15:0] output_q;
    wire read_high=(rs==R_HIGH_WAIT)||(rs==R_HIGH_CAP);
    wire [11:0] output_ra=((ra-16'h4000)>>1)+read_high;
    kwt_packed_sram #(.DW(16),.DEPTH(4096)) u_output(
        .clk(clk),.rst_n(core_rst_n),.wr(output_valid),.wa(core_out_addr[12:1]),
        .wd(core_out_addr[0]?{core_out_data,8'd0}:{8'd0,core_out_data}),
        .mask(core_out_addr[0]?4'b1100:4'b0011),.ra(output_ra),.rd(output_q));

    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            ws<=W_IDLE;wa<=0;wleft<=0;wbad<=0;axi_bresp<=0;
            input_data<=0;input_lane<=0;
        end else case(ws)
            W_IDLE: if(axi_awvalid) begin
                wa<=axi_awaddr[15:0];wleft<=axi_awlen;
                wbad<=(axi_awaddr[31:16]!=BASE_ADDR[31:16]) || axi_awlen!=0 ||
                       axi_awsize!=2 || axi_awlock!=0 || axi_awburst>1;
                axi_bresp<=(axi_awaddr[31:16]!=BASE_ADDR[31:16])?2'b11:
                          ((axi_awlen!=0||axi_awsize!=2||axi_awlock!=0||axi_awburst>1)?2'b10:2'b00);
                ws<=W_DATA;
            end
            W_DATA: if(wfire) begin
                if(axi_wlast!=(wleft==0)) axi_bresp<=2'b10;
                if(wleft!=0) wleft<=wleft-1;
                else begin
                    ws<=W_RESP;
                    if(!wbad) begin
                        if(!axi_wlast || wa[1:0]!=0) axi_bresp<=2'b10;
                        else if(axi_wstrb==0) begin end
                        else if(ctrl_word) begin
                            if(axi_wstrb[0] && !((axi_wdata[1:0]==0)||
                               ((axi_wdata[1:0]==1)&&can_start)||((axi_wdata[1:0]==2)&&can_reset)))
                                axi_bresp<=2'b10;
                        end else if(input_word) begin
                            if(axi_wstrb!=4'hf || started || (input_words>=WORDS) ||
                               ((wa-16'h1000)>>2)!=input_words) axi_bresp<=2'b10;
                            else begin input_data<=axi_wdata;input_lane<=0;ws<=W_BYTES;end
                        end else if(parameter_word) begin
                            if(!enabled_param) axi_bresp<=2'b10;
                        end else axi_bresp<=2'b10;
                    end
                end
            end
            W_BYTES: if(input_lane==3) ws<=W_RESP; else input_lane<=input_lane+1;
            W_RESP: if(axi_bready) ws<=W_IDLE;
            default: ws<=W_IDLE;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            core_start<=0;soft_reset<=0;busy<=0;done<=0;error<=0;started<=0;
            input_words<=0;parameter_words<=0;output_bytes<=0;read_words<=0;
            task_cycles<=0;task_running<=0;core_cycles_latched<=0;
        end else begin
            core_start<=start_request;soft_reset<=reset_request;
            if(reset_request) begin
                busy<=0;done<=0;error<=0;started<=0;
                input_words<=0;parameter_words<=0;output_bytes<=0;read_words<=0;
                task_cycles<=0;task_running<=0;core_cycles_latched<=0;
            end else begin
                if(task_running) task_cycles<=task_cycles+1;
                if(axi_awvalid&&axi_awready&&!started&&(input_words==0)&&
                   axi_awaddr[31:16]==BASE_ADDR[31:16]&&axi_awaddr[15:0]==16'h1000)
                    task_running<=1;
                if(ws==W_BYTES&&input_lane==3) input_words<=input_words+1;
                if(start_request) begin busy<=1;started<=1;done<=0;error<=0;end
                if(wfire&&enabled_param) parameter_words<=parameter_words+1;
                if(core_out_we&&busy) begin
                    if(output_valid) output_bytes<=output_bytes+1;
                    else error<=1;
                end
                if(core_done&&busy) begin
                    busy<=0;done<=1;
                    core_cycles_latched<=core_cycles;
                    if(output_bytes+(output_valid?1:0)!=INPUT_BYTES || parameter_words!=PARAM_WORDS || !stream_empty)
                        error<=1;
                end
                if(axi_rvalid&&axi_rready&&reading_output&&axi_rresp==0) begin
                    read_words<=read_words+1;
                    if(read_words==WORDS-1) task_running<=0;
                end
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            rs<=R_IDLE;ra<=0;rleft<=0;reading_output<=0;
            axi_rdata<=0;axi_rresp<=0;read_low<=0;
        end else case(rs)
            R_IDLE: if(axi_arvalid) begin
                ra<=axi_araddr[15:0];rleft<=axi_arlen;reading_output<=0;
                axi_rdata<=0;axi_rresp<=0;rs<=R_RESP;
                if(axi_araddr[31:16]!=BASE_ADDR[31:16]) axi_rresp<=2'b11;
                else if(axi_arlen!=0 || axi_arsize!=2 || axi_arlock!=0 ||
                        axi_arburst>1 || axi_araddr[1:0]!=0) axi_rresp<=2'b10;
                else if(axi_araddr[15:0]>=16'h4000 && axi_araddr[15:0]<16'h4000+INPUT_BYTES) begin
                    if(!done||busy||error||((axi_araddr[15:0]-16'h4000)>>2)!=read_words)
                        axi_rresp<=2'b10;
                    else begin reading_output<=1;rs<=R_LOW_WAIT;end
                end else case(axi_araddr[15:0])
                    16'h0004: axi_rdata<={24'd0,task_running,(done&&!error),
                         (parameter_words==PARAM_WORDS),(input_words==WORDS),
                         (busy&&stream_ready&&(parameter_words<PARAM_WORDS)),error,done,busy};
                    16'h0008: axi_rdata<=core_cycles_latched;
                    16'h000c: axi_rdata<=task_cycles;
                    16'h0010: axi_rdata<=input_words;
                    16'h0014: axi_rdata<=parameter_words;
                    16'h0018: axi_rdata<=output_bytes;
                    16'h001c: axi_rdata<=read_words;
                    16'h0020: axi_rdata<={8'd0,cur_layer,ld_sel,2'd0,ld_addr};
                    16'h0024: axi_rdata<=32'h4b575431;
                    default: axi_rresp<=2'b10;
                endcase
            end
            R_LOW_WAIT: rs<=R_LOW_CAP;
            R_LOW_CAP: begin read_low<=output_q;rs<=R_HIGH_WAIT;end
            R_HIGH_WAIT: rs<=R_HIGH_CAP;
            R_HIGH_CAP: begin axi_rdata<={output_q,read_low};rs<=R_RESP;end
            R_RESP: if(axi_rready) begin
                if(rleft==0) rs<=R_IDLE;
                else rleft<=rleft-1;
            end
            default: rs<=R_IDLE;
        endcase
    end
    initial begin
        if(INPUT_BYTES<4 || INPUT_BYTES>8192 || INPUT_BYTES%4!=0 || PARAM_WORDS<2 || PARAM_WORDS%2!=0 || BASE_ADDR[15:0]!=0)
            $fatal(1,"Unsupported encoder MMIO configuration");
    end
endmodule
