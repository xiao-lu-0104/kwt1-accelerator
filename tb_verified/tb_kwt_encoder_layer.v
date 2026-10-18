`timescale 1ns / 1ps
module tb_kwt_encoder_layer;
    localparam TOK = 99;
    localparam D = 64;
    localparam FF = 256;
    localparam TACT = TOK*D;      // 6336
    localparam HACT = TOK*FF;     // 25344

    reg clk = 0;
    reg rst_n = 0;
    reg start = 0;

    reg        x_we = 0;
    reg [12:0] x_addr = 0;
    reg [7:0]  x_data = 0;

    reg        p_wgt_we = 0;
    reg [2:0]  p_wgt_sel = 0;
    reg [13:0] p_wgt_addr = 0;
    reg [3:0]  p_wgt_data = 0;
    reg        p_bp_we = 0;
    reg [2:0]  p_bp_sel = 0;
    reg [7:0]  p_bp_addr = 0;
    reg signed [31:0] p_bp_bias = 0;
    reg signed [31:0] p_bp_m = 0;

    reg        p_ln_we = 0;
    reg        p_ln_sel = 0;
    reg [5:0]  p_ln_addr = 0;
    reg signed [15:0] p_ln_gamma = 0;
    reg signed [15:0] p_ln_beta = 0;

    reg signed [31:0] m_score_v = 0, m_ctx_v = 0;
    reg signed [15:0] ma1_v = 0, mb1_v = 0, ma2_v = 0, mb2_v = 0;
    reg [31:0] eps_v = 0;

    wire        out_we;
    wire [12:0] out_addr;
    wire [7:0]  out_data;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    kwt_encoder_layer dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .x_we(x_we), .x_addr(x_addr), .x_data(x_data),
        .p_wgt_we(p_wgt_we), .p_wgt_sel(p_wgt_sel),
        .p_wgt_addr(p_wgt_addr), .p_wgt_data(p_wgt_data),
        .p_bp_we(p_bp_we), .p_bp_sel(p_bp_sel), .p_bp_addr(p_bp_addr),
        .p_bp_bias(p_bp_bias), .p_bp_m(p_bp_m),
        .p_ln_we(p_ln_we), .p_ln_sel(p_ln_sel), .p_ln_addr(p_ln_addr),
        .p_ln_gamma(p_ln_gamma), .p_ln_beta(p_ln_beta), .p_ln_eps(eps_v),
        .m_score(m_score_v), .m_ctx(m_ctx_v),
        .ma1(ma1_v), .mb1(mb1_v), .ma2(ma2_v), .mb2(mb2_v),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    reg [7:0]  x_mem  [0:TACT-1];
    reg [3:0]  qw_mem [0:D*D-1];
    reg [3:0]  kw_mem [0:D*D-1];
    reg [3:0]  vw_mem [0:D*D-1];
    reg [3:0]  ow_mem [0:D*D-1];
    reg [3:0]  f1w_mem[0:D*FF-1];
    reg [3:0]  f2w_mem[0:D*FF-1];
    reg [31:0] om_mem [0:D-1], ob_mem [0:D-1];
    reg [31:0] qm_mem [0:D-1], km_mem [0:D-1], vm_mem [0:D-1];
    reg [31:0] f1m_mem[0:FF-1], f1b_mem[0:FF-1];
    reg [31:0] f2m_mem[0:D-1],  f2b_mem[0:D-1];
    reg [15:0] l1g_mem[0:D-1], l1b_mem[0:D-1];
    reg [15:0] l2g_mem[0:D-1], l2b_mem[0:D-1];
    reg [31:0] pm_mem [0:6];
    reg [7:0]  e_mem  [0:TACT-1];
    reg [7:0]  cap    [0:TACT-1];

    integer i, errors, timeout, got;
    integer at_cnt, ln_cnt, f1_cnt, f2_cnt;
    integer al_dbg;

    reg [4:0] last_state = 5'd0;
    integer st_dbg = 0;
    always @(negedge clk) if (dut.state !== last_state) begin
        if (st_dbg < 24) $display("  state %0d -> %0d @%0d", last_state, dut.state, cycle_count);
        last_state = dut.state;
        st_dbg = st_dbg + 1;
    end

    always @(negedge clk) if (dut.state == 5'd2) begin
        if (al_dbg < 3) $display("  align1: cnt=%0d y0=%0d y1=%0d y2=%0d y3=%0d",
            dut.cnt, $signed(dut.al_y0), $signed(dut.al_y1),
            $signed(dut.al_y2), $signed(dut.al_y3));
        al_dbg = al_dbg + 1;
    end

    always @(negedge clk) begin
        if (dut.at_out_we) begin
            if (at_cnt < 3) $display("  at out %0d: addr=%0d data=%08x", at_cnt, dut.at_out_addr, dut.at_out_data);
            at_cnt = at_cnt + 1;
        end
        if (dut.ln_out_we) begin
            if (ln_cnt < 3) $display("  ln out %0d: addr=%0d data=%0d", ln_cnt, dut.ln_out_addr, $signed(dut.ln_out_data));
            ln_cnt = ln_cnt + 1;
        end
        if (dut.f1_out_we) f1_cnt = f1_cnt + 1;
        if (dut.f2_out_we) f2_cnt = f2_cnt + 1;
    end

    always @(negedge clk) if (out_we) begin
        cap[out_addr] = out_data;
        got = got + 1;
    end

    task load_wgt(input [2:0] s, input integer n);
        begin
            for (i = 0; i < n; i = i + 1) begin
                @(negedge clk);
                p_wgt_we = 1; p_wgt_sel = s; p_wgt_addr = i[13:0];
                case (s)
                    3'd0: p_wgt_data = qw_mem[i];
                    3'd1: p_wgt_data = kw_mem[i];
                    3'd2: p_wgt_data = vw_mem[i];
                    3'd3: p_wgt_data = ow_mem[i];
                    3'd4: p_wgt_data = f1w_mem[i];
                    default: p_wgt_data = f2w_mem[i];
                endcase
            end
            @(negedge clk); p_wgt_we = 0;
        end
    endtask

    task load_bp(input [2:0] s, input integer n);
        begin
            for (i = 0; i < n; i = i + 1) begin
                @(negedge clk);
                p_bp_we = 1; p_bp_sel = s; p_bp_addr = i[7:0];
                case (s)
                    3'd0: begin p_bp_m = $signed(qm_mem[i]); p_bp_bias = 0; end
                    3'd1: begin p_bp_m = $signed(km_mem[i]); p_bp_bias = 0; end
                    3'd2: begin p_bp_m = $signed(vm_mem[i]); p_bp_bias = 0; end
                    3'd3: begin p_bp_m = $signed(om_mem[i]);  p_bp_bias = $signed(ob_mem[i]);  end
                    3'd4: begin p_bp_m = $signed(f1m_mem[i]); p_bp_bias = $signed(f1b_mem[i]); end
                    default: begin p_bp_m = $signed(f2m_mem[i]); p_bp_bias = $signed(f2b_mem[i]); end
                endcase
            end
            @(negedge clk); p_bp_we = 0;
        end
    endtask

    task load_ln(input s);
        begin
            for (i = 0; i < D; i = i + 1) begin
                @(negedge clk);
                p_ln_we = 1; p_ln_sel = s; p_ln_addr = i[5:0];
                if (s == 1'b0) begin
                    p_ln_gamma = $signed(l1g_mem[i]); p_ln_beta = $signed(l1b_mem[i]);
                end else begin
                    p_ln_gamma = $signed(l2g_mem[i]); p_ln_beta = $signed(l2b_mem[i]);
                end
            end
            @(negedge clk); p_ln_we = 0;
        end
    endtask

    initial begin
        errors = 0; got = 0;
        at_cnt = 0; ln_cnt = 0; f1_cnt = 0; f2_cnt = 0; al_dbg = 0;
        $readmemh("vectors/enc/x.mem", x_mem);
        $readmemh("vectors/enc/q_wgt.mem", qw_mem);
        $readmemh("vectors/enc/k_wgt.mem", kw_mem);
        $readmemh("vectors/enc/v_wgt.mem", vw_mem);
        $readmemh("vectors/enc/o_wgt.mem", ow_mem);
        $readmemh("vectors/enc/f1_wgt.mem", f1w_mem);
        $readmemh("vectors/enc/f2_wgt.mem", f2w_mem);
        $readmemh("vectors/enc/o_m.mem", om_mem);
        $readmemh("vectors/enc/o_b.mem", ob_mem);
        $readmemh("vectors/enc/q_m.mem", qm_mem);
        $readmemh("vectors/enc/k_m.mem", km_mem);
        $readmemh("vectors/enc/v_m.mem", vm_mem);
        $readmemh("vectors/enc/f1_m.mem", f1m_mem);
        $readmemh("vectors/enc/f1_b.mem", f1b_mem);
        $readmemh("vectors/enc/f2_m.mem", f2m_mem);
        $readmemh("vectors/enc/f2_b.mem", f2b_mem);
        $readmemh("vectors/enc/ln1_g.mem", l1g_mem);
        $readmemh("vectors/enc/ln1_b.mem", l1b_mem);
        $readmemh("vectors/enc/ln2_g.mem", l2g_mem);
        $readmemh("vectors/enc/ln2_b.mem", l2b_mem);
        $readmemh("vectors/enc/params.mem", pm_mem);
        $readmemh("vectors/enc/expect.mem", e_mem);
        if (x_mem[0] === 8'hxx || e_mem[0] === 8'hxx) begin
            $display("FAIL: vectors missing");
            $finish;
        end
        m_score_v = $signed(pm_mem[0]);
        m_ctx_v   = $signed(pm_mem[1]);
        ma1_v     = $signed(pm_mem[2][15:0]);
        mb1_v     = $signed(pm_mem[3][15:0]);
        ma2_v     = $signed(pm_mem[4][15:0]);
        mb2_v     = $signed(pm_mem[5][15:0]);
        eps_v     = pm_mem[6];

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        for (i = 0; i < TACT; i = i + 1) begin
            @(negedge clk);
            x_we = 1; x_addr = i[12:0]; x_data = x_mem[i];
        end
        @(negedge clk); x_we = 0;

        load_wgt(3'd0, D*D);
        load_wgt(3'd1, D*D);
        load_wgt(3'd2, D*D);
        load_wgt(3'd3, D*D);
        load_wgt(3'd4, D*FF);
        load_wgt(3'd5, D*FF);
        load_bp(3'd0, D);
        load_bp(3'd1, D);
        load_bp(3'd2, D);
        load_bp(3'd3, D);
        load_bp(3'd4, FF);
        load_bp(3'd5, D);
        load_ln(1'b0);
        load_ln(1'b1);

        @(negedge clk); start = 1;
        timeout = 0;
        while (!done && timeout < 3000000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end
        @(negedge clk);
        start = 0;

        if (!done) begin
            $display("FAIL: timeout");
            errors = errors + 1;
        end
        $display("cycles=%0d outputs=%0d (expect %0d)", cycle_count, got, TACT);
        $display("  cnts: at=%0d ln=%0d f1=%0d f2=%0d", at_cnt, ln_cnt, f1_cnt, f2_cnt);
        $display("  attn x_buf[0..3]=%0d %0d %0d %0d", $signed(dut.u_attn.x_buf[0]),
                 $signed(dut.u_attn.x_buf[1]), $signed(dut.u_attn.x_buf[2]), $signed(dut.u_attn.x_buf[3]));
        $display("  q engine: wgt[0]=%0d act[0]=%0d m[0]=%0d",
                 $signed(dut.u_attn.u_qkv.u_q.wgt_buf[0]),
                 $signed(dut.u_attn.u_qkv.u_q.act_buf[0]),
                 $signed(dut.u_attn.u_qkv.u_q.m_buf[0]));
        $display("  attn q_buf[0..3]=%0d %0d %0d %0d", $signed(dut.u_attn.q_buf[0]),
                 $signed(dut.u_attn.q_buf[1]), $signed(dut.u_attn.q_buf[2]), $signed(dut.u_attn.q_buf[3]));
        $display("  attn p_buf[0..3]=%0d %0d %0d %0d", $signed(dut.u_attn.p_buf[0]),
                 $signed(dut.u_attn.p_buf[1]), $signed(dut.u_attn.p_buf[2]), $signed(dut.u_attn.p_buf[3]));
        $display("  attn ctx[0..3]  =%0d %0d %0d %0d", $signed(dut.u_attn.ctx_buf[0]),
                 $signed(dut.u_attn.ctx_buf[1]), $signed(dut.u_attn.ctx_buf[2]), $signed(dut.u_attn.ctx_buf[3]));
        $display("  o_buf[0..3]=%0d %0d %0d %0d", $signed(dut.o_buf[0]), $signed(dut.o_buf[1]),
                 $signed(dut.o_buf[2]), $signed(dut.o_buf[3]));
        $display("  r1[0..3] =%0d %0d %0d %0d", $signed(dut.r1_buf[0]), $signed(dut.r1_buf[1]),
                 $signed(dut.r1_buf[2]), $signed(dut.r1_buf[3]));
        $display("  ln_g[0][0..3]=%0d %0d %0d %0d  ln_param_gamma=%0d",
                 $signed(dut.ln_g[0][0]), $signed(dut.ln_g[0][1]),
                 $signed(dut.ln_g[0][2]), $signed(dut.ln_g[0][3]),
                 $signed(dut.u_ln.gamma_q[0]));
        $display("  ln in_buf[0..3]=%0d %0d %0d %0d", $signed(dut.u_ln.x_buf[0]),
                 $signed(dut.u_ln.x_buf[1]), $signed(dut.u_ln.x_buf[2]), $signed(dut.u_ln.x_buf[3]));
        $display("  x1[0..3]=%0d %0d %0d %0d", $signed(dut.x1_buf[0]), $signed(dut.x1_buf[1]),
                 $signed(dut.x1_buf[2]), $signed(dut.x1_buf[3]));
        $display("  h[0..3] =%0d %0d %0d %0d", $signed(dut.h_buf[0]), $signed(dut.h_buf[1]),
                 $signed(dut.h_buf[2]), $signed(dut.h_buf[3]));
        $display("  f[0..3] =%0d %0d %0d %0d", $signed(dut.f_buf[0]), $signed(dut.f_buf[1]),
                 $signed(dut.f_buf[2]), $signed(dut.f_buf[3]));

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

        if (errors == 0) $display("PASS: encoder layer %0d values bit-exact", TACT);
        else $display("FAIL: %0d errors", errors);
        $finish;
    end
endmodule
