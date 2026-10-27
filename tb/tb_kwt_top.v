`timescale 1ns / 1ps
module tb_kwt_top;
    localparam TOK = 99;
    localparam D = 64;
    localparam FF = 256;
    localparam NL = 12;
    localparam TP = 98;
    localparam TACT = TOK*D;      // 6336
    localparam PACT = TP*D;       // 6272
    localparam NW4 = D*D;
    localparam NWF = D*FF;
    localparam WLAYER = 4*NW4 + 2*NWF;
    localparam BLAYER = 3*D + D + FF + D;
    localparam LLAYER = 2*D;

    reg clk = 0;
    reg rst_n = 0;
    reg start = 0;

    reg        mf_we = 0;
    reg [12:0] mf_addr = 0;
    reg [7:0]  mf_data = 0;

    reg        pp_wgt_we = 0;
    reg [11:0] pp_wgt_addr = 0;
    reg [3:0]  pp_wgt_data = 0;
    reg        pp_bp_we = 0;
    reg [5:0]  pp_bp_addr = 0;
    reg signed [31:0] pp_bp_bias = 0;
    reg signed [31:0] pp_bp_m = 0;

    reg        cp_we = 0;
    reg [12:0] cp_addr = 0;
    reg [7:0]  cp_data = 0;

    reg        hd_wgt_we = 0;
    reg [9:0]  hd_wgt_addr = 0;
    reg [3:0]  hd_wgt_data = 0;
    reg        hd_bp_we = 0;
    reg [3:0]  hd_bp_addr = 0;
    reg signed [31:0] hd_bp_bias = 0;
    reg signed [31:0] hd_bp_m = 0;

    wire [3:0]  cur_layer;
    wire [3:0]  ld_sel;
    wire [13:0] ld_addr;

    wire [3:0]  pred_class;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    // ---- encoder parameter ROM ----
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

    wire [3:0]  rom_wgt   = (ld_sel < 4'd6) ? wrom[widx] : 4'd0;
    wire [63:0] rom_wgt16 = (ld_sel < 4'd6) ? {
        wrom[widx+19'd15], wrom[widx+19'd14], wrom[widx+19'd13], wrom[widx+19'd12],
        wrom[widx+19'd11], wrom[widx+19'd10], wrom[widx+19'd9],  wrom[widx+19'd8],
        wrom[widx+19'd7],  wrom[widx+19'd6],  wrom[widx+19'd5],  wrom[widx+19'd4],
        wrom[widx+19'd3],  wrom[widx+19'd2],  wrom[widx+19'd1],  wrom[widx] } : 64'd0;
    wire signed [31:0] rom_m    = (ld_sel >= 4'd6 && ld_sel <= 4'd9) ? $signed(bmrom[bidx])
                                : (ld_sel == 4'd12) ? $signed(lcrom[cidx]) : 32'sd0;
    wire signed [31:0] rom_bias = (ld_sel >= 4'd6 && ld_sel <= 4'd9) ? $signed(bbrom[bidx])
                                : 32'sd0;
    wire signed [15:0] rom_ln_gamma = (ld_sel == 4'd10 || ld_sel == 4'd11) ? $signed(lgrom[lidx]) : 16'sd0;
    wire signed [15:0] rom_ln_beta  = (ld_sel == 4'd10 || ld_sel == 4'd11) ? $signed(lbrom[lidx]) : 16'sd0;

    kwt_top dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .mf_we(mf_we), .mf_addr(mf_addr), .mf_data(mf_data),
        .pp_wgt_we(pp_wgt_we), .pp_wgt_addr(pp_wgt_addr), .pp_wgt_data(pp_wgt_data),
        .pp_bp_we(pp_bp_we), .pp_bp_addr(pp_bp_addr),
        .pp_bp_bias(pp_bp_bias), .pp_bp_m(pp_bp_m),
        .cp_we(cp_we), .cp_addr(cp_addr), .cp_data(cp_data),
        .cur_layer(cur_layer), .ld_sel(ld_sel), .ld_addr(ld_addr),
        .rom_wgt(rom_wgt), .rom_wgt16(rom_wgt16), .rom_bias(rom_bias), .rom_m(rom_m),
        .rom_ln_gamma(rom_ln_gamma), .rom_ln_beta(rom_ln_beta),
        .hd_wgt_we(hd_wgt_we), .hd_wgt_addr(hd_wgt_addr), .hd_wgt_data(hd_wgt_data),
        .hd_bp_we(hd_bp_we), .hd_bp_addr(hd_bp_addr),
        .hd_bp_bias(hd_bp_bias), .hd_bp_m(hd_bp_m),
        .pred_class(pred_class), .done(done), .cycle_count(cycle_count)
    );

    reg [7:0]  mf_mem [0:3*PACT-1];
    reg [3:0]  pw_mem [0:NW4-1];
    reg [31:0] pm_mem [0:D-1], pb_mem [0:D-1];
    reg [7:0]  cp_mem [0:TACT-1];
    reg [3:0]  hw_mem [0:1023];
    reg [31:0] hm_mem [0:15], hb_mem [0:15];
    reg [31:0] e_mem  [0:2];
    reg [7:0]  x_mem  [0:TACT-1];

    integer i, errors, timeout, ns, pass_cnt;
    integer eow_cnt = 0, ppw_cnt = 0, hdw_cnt = 0, xw_cnt = 0; integer cl_dbg = 0; integer gv_dbg = 0; always @(negedge clk) if (dut.u_head.gemm_valid && gv_dbg < 4) begin $display("  hd gemm valid: acc=%0d %0d %0d %0d g_lat=%0d act0=%0d wgt0=%0d", $signed(dut.u_head.acc0), $signed(dut.u_head.acc1), $signed(dut.u_head.acc2), $signed(dut.u_head.acc3), dut.u_head.g_lat, $signed(dut.u_head.act_flat[7:0]), $signed(dut.u_head.wgt_flat[3:0])); gv_dbg = gv_dbg + 1; end always @(negedge clk) if (dut.state == 4'd3 && cl_dbg < 3) begin $display("  CLS: we=%b addr=%0d data=%0d", dut.enc_x_we, dut.enc_x_addr, $signed(dut.enc_x_data)); cl_dbg = cl_dbg + 1; end
    always @(negedge clk) begin
        if (dut.enc_out_we) begin
            if (eow_cnt < 3) $display("  enc out %0d: addr=%0d data=%0d", eow_cnt,
                dut.enc_out_addr, $signed(dut.enc_out_data));
            eow_cnt = eow_cnt + 1;
        end
        if (dut.pp_out_we)  ppw_cnt = ppw_cnt + 1;
        if (dut.hd_out_we) begin if (hdw_cnt < 4) $display("  hd out %0d: addr=%0d data=%08x", hdw_cnt, dut.hd_out_addr, dut.hd_out_data); hdw_cnt = hdw_cnt + 1; end if (dut.enc_x_we) xw_cnt = xw_cnt + 1;
    end

    initial begin
        errors = 0;
        $readmemh("vectors/top/mfcc.mem", mf_mem);
        $readmemh("vectors/top/pp_wgt.mem", pw_mem);
        $readmemh("vectors/top/pp_m.mem", pm_mem);
        $readmemh("vectors/top/pp_b.mem", pb_mem);
        $readmemh("vectors/top/cp.mem", cp_mem);
        $readmemh("vectors/top/hd_wgt.mem", hw_mem);
        $readmemh("vectors/top/hd_m.mem", hm_mem);
        $readmemh("vectors/top/hd_b.mem", hb_mem);
        $readmemh("vectors/top/expect.mem", e_mem);
        $readmemh("vectors/enc12/wrom.mem", wrom);
        $readmemh("vectors/enc12/brom_m.mem", bmrom);
        $readmemh("vectors/enc12/brom_b.mem", bbrom);
        $readmemh("vectors/enc12/lnrom_g.mem", lgrom);
        $readmemh("vectors/enc12/lnrom_b.mem", lbrom);
        $readmemh("vectors/enc12/lconst.mem", lcrom);
        if (mf_mem[0] === 8'hxx || e_mem[0] === 32'hx) begin
            $display("FAIL: vectors missing");
            $finish;
        end

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        // MFCC
        for (i = 0; i < PACT; i = i + 1) begin
            @(negedge clk);
            mf_we = 1; mf_addr = i[12:0]; mf_data = mf_mem[i];
        end
        @(negedge clk); mf_we = 0;

        // patch projection weights
        for (i = 0; i < NW4; i = i + 1) begin
            @(negedge clk);
            pp_wgt_we = 1; pp_wgt_addr = i[11:0]; pp_wgt_data = pw_mem[i];
        end
        @(negedge clk); pp_wgt_we = 0;
        for (i = 0; i < D; i = i + 1) begin
            @(negedge clk);
            pp_bp_we = 1; pp_bp_addr = i[5:0];
            pp_bp_m = $signed(pm_mem[i]); pp_bp_bias = $signed(pb_mem[i]);
        end
        @(negedge clk); pp_bp_we = 0;

        // class token + posit
        for (i = 0; i < TACT; i = i + 1) begin
            @(negedge clk);
            cp_we = 1; cp_addr = i[12:0]; cp_data = cp_mem[i];
        end
        @(negedge clk); cp_we = 0;

        // head weights
        for (i = 0; i < 1024; i = i + 1) begin
            @(negedge clk);
            hd_wgt_we = 1; hd_wgt_addr = i[9:0]; hd_wgt_data = hw_mem[i];
        end
        @(negedge clk); hd_wgt_we = 0;
        for (i = 0; i < 16; i = i + 1) begin
            @(negedge clk);
            hd_bp_we = 1; hd_bp_addr = i[3:0];
            hd_bp_m = $signed(hm_mem[i]); hd_bp_bias = $signed(hb_mem[i]);
        end
        @(negedge clk); hd_bp_we = 0;

        // ---- run all samples ----
        pass_cnt = 0;
        for (ns = 0; ns < 3; ns = ns + 1) begin
            // MFCC for this sample
            for (i = 0; i < PACT; i = i + 1) begin
                @(negedge clk);
                mf_we = 1; mf_addr = i[12:0]; mf_data = mf_mem[ns*PACT + i];
            end
            @(negedge clk); mf_we = 0;

            @(negedge clk); start = 1;
            timeout = 0;
            while (!done && timeout < 15000000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            @(negedge clk);
            start = 0;

            if (!done) begin
                $display("FAIL: timeout sample %0d layer %0d state %0d", ns, cur_layer, dut.state);
                errors = errors + 1;
            end else begin
                if (ns == 0)
                    $display("cycles=%0d  (%.2f ms @150MHz)", cycle_count, cycle_count / 150000.0);
                if (pred_class === e_mem[ns][3:0]) begin
                    pass_cnt = pass_cnt + 1;
                    $display("  sample %0d: pred=%0d expect=%0d  OK", ns, pred_class, e_mem[ns]);
                end else begin
                    $display("  sample %0d: pred=%0d expect=%0d  MISMATCH", ns, pred_class, e_mem[ns]);
                    errors = errors + 1;
                end
            end
            repeat (5) @(negedge clk);
        end

        if (errors == 0) $display("PASS: full KWT-1 inference, %0d/3 samples", pass_cnt);
        else $display("FAIL: %0d errors", errors);
        $finish;
    end
endmodule
