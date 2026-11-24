`timescale 1ns / 1ps
module tb_kwt_encoder_12 #(parameter COMPACT=1, parameter PARAM_HANDSHAKE=0,
                         parameter PARAM_STALL=0, parameter PARAM_SERIAL=0);
    localparam TOK = 99;
    localparam D = 64;
    localparam FF = 256;
    localparam NL = 12;
    localparam TACT = TOK*D;
    localparam NW4 = D*D;
    localparam NWF = D*FF;
    localparam WLAYER = 4*NW4 + 2*NWF;   // 49152
    localparam BLAYER = 3*D + D + FF + D;   // 576
    localparam LLAYER = 2*D;             // 128

    reg clk = 0;
    reg rst_n = 0;
    reg start = 0;

    reg        x_we = 0;
    reg [12:0] x_addr = 0;
    reg [7:0]  x_data = 0;

    wire [3:0]  cur_layer;
    wire [3:0]  ld_sel;
    wire [13:0] ld_addr;
    wire        out_we;
    wire [12:0] out_addr;
    wire [7:0]  out_data;
    wire        done;
    wire [31:0] cycle_count;
    wire param_ready;
    reg [7:0] transfer_clock=0;
    always @(posedge clk) transfer_clock<=transfer_clock+1;
    wire offer_word=!PARAM_STALL || transfer_clock[2:0]==0 || transfer_clock[2:0]==3 || transfer_clock[2:0]==6;
    reg [31:0] stream_words[0:NL*3782*2-1];
    reg serial_valid=0;
    integer serial_words_sent=0;
    wire serial_ready,record_valid,stream_empty;
    wire [63:0] serial_record;
    kwt_param_stream param_stream(.clk(clk),.rst_n(rst_n),
        .s_valid(serial_valid),.s_ready(serial_ready),.s_data(stream_words[(serial_words_sent<NL*3782*2)?serial_words_sent:0]),
        .m_valid(record_valid),.m_ready(param_ready),.m_data(serial_record),.empty(stream_empty));
    wire serial_fire=serial_valid&&serial_ready;
    always @(posedge clk) begin
        if(!rst_n) begin serial_valid<=0; serial_words_sent<=0; end
        else if(PARAM_SERIAL) begin
            if(serial_fire) serial_words_sent<=serial_words_sent+1;
            if(!serial_valid || serial_ready)
                serial_valid<=start && (serial_words_sent+(serial_fire?1:0)<NL*3782*2) && offer_word;
        end
    end
    wire param_valid=PARAM_SERIAL?record_valid:offer_word;
    integer parameter_beats=0,parameter_waits=0;
    always @(posedge clk) if(rst_n) begin
        if(dut.loading && (!PARAM_HANDSHAKE || param_valid)) parameter_beats=parameter_beats+1;
        if(param_ready&&!param_valid) parameter_waits=parameter_waits+1;
    end

    always #5 clk = ~clk;

    reg [3:0]  wrom [0:NL*WLAYER-1];
    reg [31:0] bmrom[0:NL*BLAYER-1];
    reg [31:0] bbrom[0:NL*BLAYER-1];
    reg [15:0] lgrom [0:NL*LLAYER-1];
    reg [15:0] lbrom [0:NL*LLAYER-1];
    reg [31:0] lcrom [0:NL*6-1];

    function [18:0] woff(input [3:0] s);
        case (s)
            4'd0: woff = 19'd0;
            4'd1: woff = 19'd4096;
            4'd2: woff = 19'd8192;
            4'd3: woff = 19'd12288;
            4'd4: woff = 19'd16384;
            default: woff = 19'd32768;
        endcase
    endfunction

    function [9:0] boff(input [3:0] s);
        case (s)
            4'd6: boff = 10'd0;
            4'd7: boff = 10'd192;
            4'd8: boff = 10'd256;
            default: boff = 10'd512;
        endcase
    endfunction

    wire [19:0] widx = cur_layer * WLAYER + woff(ld_sel) + ld_addr;
    wire [12:0] bidx = cur_layer * BLAYER + boff(ld_sel) + ld_addr;
    wire [11:0] lidx = cur_layer * LLAYER +
                       ((ld_sel == 4'd11) ? 12'd64 : 12'd0) + ld_addr;
    wire [6:0]  cidx = cur_layer * 6 + ld_addr;

    wire [3:0]  raw_wgt   = (ld_sel < 4'd6) ? wrom[widx] : 4'd0;
    wire [63:0] raw_wgt16 = (ld_sel < 4'd6) ? {
        wrom[widx+19'd15], wrom[widx+19'd14], wrom[widx+19'd13], wrom[widx+19'd12],
        wrom[widx+19'd11], wrom[widx+19'd10], wrom[widx+19'd9],  wrom[widx+19'd8],
        wrom[widx+19'd7],  wrom[widx+19'd6],  wrom[widx+19'd5],  wrom[widx+19'd4],
        wrom[widx+19'd3],  wrom[widx+19'd2],  wrom[widx+19'd1],  wrom[widx] } : 64'd0;
    wire signed [31:0] raw_m    = (ld_sel >= 4'd6 && ld_sel <= 4'd9) ? $signed(bmrom[bidx])
                                : (ld_sel == 4'd12) ? $signed(lcrom[cidx]) : 32'sd0;
    wire signed [31:0] raw_bias = (ld_sel >= 4'd6 && ld_sel <= 4'd9) ? $signed(bbrom[bidx])
                                : 32'sd0;
    wire signed [15:0] raw_ln_gamma = (ld_sel == 4'd10 || ld_sel == 4'd11) ? $signed(lgrom[lidx]) : 16'sd0;
    wire signed [15:0] raw_ln_beta  = (ld_sel == 4'd10 || ld_sel == 4'd11) ? $signed(lbrom[lidx]) : 16'sd0;
    wire [3:0] rom_wgt=param_valid?(PARAM_SERIAL?serial_record[3:0]:raw_wgt):4'hx;
    wire [63:0] rom_wgt16=param_valid?(PARAM_SERIAL?serial_record:raw_wgt16):64'hxxxxxxxxxxxxxxxx;
    wire signed [31:0] rom_m=param_valid?(PARAM_SERIAL?serial_record[63:32]:raw_m):32'hxxxxxxxx;
    wire signed [31:0] rom_bias=param_valid?(PARAM_SERIAL?serial_record[31:0]:raw_bias):32'hxxxxxxxx;
    wire signed [15:0] rom_ln_gamma=param_valid?(PARAM_SERIAL?serial_record[15:0]:raw_ln_gamma):16'hxxxx;
    wire signed [15:0] rom_ln_beta=param_valid?(PARAM_SERIAL?serial_record[31:16]:raw_ln_beta):16'hxxxx;

    kwt_encoder_12 #(.COMPACT(COMPACT),.PARAM_HANDSHAKE(PARAM_HANDSHAKE)) dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .x_we(x_we), .x_addr(x_addr), .x_data(x_data),
        .cur_layer(cur_layer), .ld_sel(ld_sel), .ld_addr(ld_addr),
        .rom_wgt(rom_wgt), .rom_wgt16(rom_wgt16), .rom_bias(rom_bias), .rom_m(rom_m),
        .rom_ln_gamma(rom_ln_gamma), .rom_ln_beta(rom_ln_beta),
        .param_valid(param_valid),.param_ready(param_ready),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    reg [7:0] xm_mem [0:TACT-1];
    reg [7:0] e_mem  [0:TACT-1];
    reg [7:0] cap    [0:TACT-1];

    integer i, errors, timeout, got;
    integer ld_seen, st_cnt, nstart, ndone;
    integer mac_issues=0;
    generate if(COMPACT) begin: g_profile
        always @(posedge clk) if(rst_n&&dut.g_compact.u_enc.mac_issue)
            mac_issues=mac_issues+1;
    end endgenerate
    reg [3:0] last_st = 4'd0;
    reg [3:0] last_L = 4'd15;

    always @(negedge clk) begin
        if (dut.enc_start) nstart = nstart + 1;
        if (dut.enc_done) ndone = ndone + 1;
        if (cur_layer !== last_L) begin
            $display("  layer -> %0d @%0d", cur_layer, cycle_count);
            last_L = cur_layer;
        end
        if (out_we) begin
            cap[out_addr] = out_data;
            got = got + 1;
        end
    end

    integer xf_dbg = 0;
    integer eo_dbg = 0;
    always @(negedge clk) if (dut.enc_out_we && eo_dbg < 3) begin
        $display("  enc out L%0d: addr=%0d data=%0d", cur_layer, dut.enc_out_addr, $signed(dut.enc_out_data));
        eo_dbg = eo_dbg + 1;
    end
    always @(negedge clk) if (dut.state == 4'd8 && xf_dbg < 3) begin
        $display("  XF L%0d: m_score=%0d m_ctx=%0d ma1=%0d xin0=%0d",
            cur_layer, $signed(dut.m_score_r), $signed(dut.m_ctx_r),
            $signed(dut.ma1_r), $signed(dut.xin_data));
        xf_dbg = xf_dbg + 1;
    end

    initial begin
        errors = 0; got = 0; ld_seen = 0; st_cnt = 0; nstart = 0; ndone = 0;
        $readmemh("vectors/enc12/wrom.mem", wrom);
        $readmemh("vectors/enc12/brom_m.mem", bmrom);
        $readmemh("vectors/enc12/brom_b.mem", bbrom);
        $readmemh("vectors/enc12/lnrom_g.mem", lgrom);
        $readmemh("vectors/enc12/lnrom_b.mem", lbrom);
        $readmemh("vectors/enc12/lconst.mem", lcrom);
        $readmemh("vectors/enc12/x.mem", xm_mem);
        $readmemh("vectors/enc12/expect.mem", e_mem);
        if(PARAM_SERIAL) begin
            $readmemh("vectors/enc12/param_stream.mem", stream_words);
            if(stream_words[0]===32'hxxxxxxxx || stream_words[NL*3782*2-1]===32'hxxxxxxxx)
                $fatal(1,"Packed parameter stream missing");
        end
        if (xm_mem[0] === 8'hxx || e_mem[0] === 8'hxx) begin
            $display("FAIL: vectors missing");
            $finish;
        end

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        for (i = 0; i < TACT; i = i + 1) begin
            @(negedge clk);
            x_we = 1; x_addr = i[12:0]; x_data = xm_mem[i];
        end
        @(negedge clk); x_we = 0;
        @(negedge clk);
        @(negedge clk); start = 1;
        timeout = 0;
        while (!done && timeout < 12000000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end
        @(negedge clk);
        start = 0;

        if (!done) begin
            $display("FAIL: timeout at layer %0d", cur_layer);
            errors = errors + 1;
        end
        $display("cycles=%0d outputs=%0d (expect %0d) starts=%0d dones=%0d", cycle_count, got, TACT, nstart, ndone);
        $display("  -- %.2f ms @150MHz", cycle_count / 150000.0);
        if(COMPACT) begin
            $display("PARAM_TRANSFER accepted=%0d stalls=%0d expected_cycles=%0d",parameter_beats,parameter_waits,3159181+parameter_waits);
            if(parameter_beats!=NL*3782 || cycle_count!=3159181+parameter_waits) begin
                $display("FAIL: parameter beat count or stall cycle accounting");
                errors=errors+1;
            end
            if(PARAM_SERIAL) begin
                $display("PARAM_SERIAL_WORDS accepted=%0d",serial_words_sent);
                if(serial_words_sent!=NL*3782*2 || !stream_empty) begin
                    $display("FAIL: parameter serial stream not fully consumed");
                    errors=errors+1;
                end
            end
            $display("PROFILE encoder_MAC_issues=%0d useful_MACs=73446912 useful_util_pct=%.3f issue_util_pct=%.3f",
                mac_issues,100.0*73446912/(64.0*cycle_count),100.0*mac_issues/cycle_count);
            if(mac_issues!=1183248) begin
                $display("FAIL: unexpected encoder issued-work count");
                errors=errors+1;
            end
        end
        repeat (5) @(negedge clk);
        if (got != TACT) begin
            $display("FAIL: output count");
            errors = errors + 1;
        end
        for (i = 0; i < TACT; i = i + 1) begin
            if (cap[i] !== e_mem[i]) begin
                if (errors < 6)
                    $display("MISMATCH [%0d] got %0d exp %0d", i, $signed(cap[i]), $signed(e_mem[i]));
                errors = errors + 1;
            end
        end

        if (errors == 0) $display("PASS: 12-layer encoder %0d values bit-exact", TACT);
        else $display("FAIL: %0d errors", errors);
        $finish;
    end
endmodule

module tb_kwt_encoder_12_stall;
    tb_kwt_encoder_12 #(.PARAM_HANDSHAKE(1),.PARAM_STALL(1),.PARAM_SERIAL(1)) test();
endmodule
