`timescale 1ns / 1ps
module tb_kwt_attention;
    localparam TOK = 99;
    localparam D = 64;
    localparam TACT = TOK*D;      // 6336
    localparam NWGT = D*D;        // 4096
    localparam N_WORD = TOK*(D/4); // 1584

    reg clk = 0;
    reg rst_n = 0;
    reg start = 0;

    reg        x_we = 0;
    reg [12:0] x_addr = 0;
    reg [7:0]  x_data = 0;

    reg        p_wgt_we = 0;
    reg [1:0]  p_wgt_sel = 0;
    reg [13:0] p_wgt_addr = 0;
    reg [3:0]  p_wgt_data = 0;
    reg        p_bp_we = 0;
    reg [1:0]  p_bp_sel = 0;
    reg [7:0]  p_bp_addr = 0;
    reg signed [31:0] p_bp_bias = 0;
    reg signed [31:0] p_bp_m = 0;

    reg signed [31:0] m_score_v = 0;
    reg signed [31:0] m_ctx_v = 0;

    wire        out_we;
    wire [12:0] out_addr;
    wire [31:0] out_data;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    kwt_attention dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .x_we(x_we), .x_addr(x_addr), .x_data(x_data),
        .p_wgt_we(p_wgt_we), .p_wgt_sel(p_wgt_sel),
        .p_wgt_addr(p_wgt_addr), .p_wgt_data(p_wgt_data),
        .p_wgt_we16(1'b0), .p_wgt_data16(64'd0),
        .p_bp_we(p_bp_we), .p_bp_sel(p_bp_sel), .p_bp_addr(p_bp_addr),
        .p_bp_bias(p_bp_bias), .p_bp_m(p_bp_m),
        .m_score(m_score_v),
        .m_ctx(m_ctx_v),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    reg [7:0]  x_mem [0:TACT-1];
    reg [3:0]  qw_mem [0:NWGT-1];
    reg [3:0]  kw_mem [0:NWGT-1];
    reg [3:0]  vw_mem [0:NWGT-1];
    reg [3:0]  ow_mem [0:NWGT-1];
    reg [31:0] qm_mem [0:D-1];
    reg [31:0] km_mem [0:D-1];
    reg [31:0] vm_mem [0:D-1];
    reg [31:0] om_mem [0:D-1];
    reg [31:0] qb_mem [0:D-1];
    reg [31:0] kb_mem [0:D-1];
    reg [31:0] vb_mem [0:D-1];
    reg [31:0] ob_mem [0:D-1];
    reg [31:0] sm_mem [0:0];
    reg [31:0] cm_mem [0:0];
    reg [31:0] e_mem [0:N_WORD-1];
    reg [31:0] cap   [0:N_WORD-1];

    integer i, errors, timeout, got, sel;

    always @(negedge clk) if (out_we) begin
        cap[out_addr] = out_data;
        got = got + 1;
    end

    task load_wgt(input [1:0] s, input integer n);
        begin
            for (i = 0; i < n; i = i + 1) begin
                @(negedge clk);
                p_wgt_we = 1; p_wgt_sel = s; p_wgt_addr = i[13:0];
                case (s)
                    2'd0: p_wgt_data = qw_mem[i];
                    2'd1: p_wgt_data = kw_mem[i];
                    2'd2: p_wgt_data = vw_mem[i];
                    default: p_wgt_data = ow_mem[i];
                endcase
            end
            @(negedge clk); p_wgt_we = 0;
        end
    endtask

    task load_bp(input [1:0] s);
        begin
            for (i = 0; i < D; i = i + 1) begin
                @(negedge clk);
                p_bp_we = 1; p_bp_sel = s; p_bp_addr = i[7:0];
                case (s)
                    2'd0: begin p_bp_m = $signed(qm_mem[i]); p_bp_bias = $signed(qb_mem[i]); end
                    2'd1: begin p_bp_m = $signed(km_mem[i]); p_bp_bias = $signed(kb_mem[i]); end
                    2'd2: begin p_bp_m = $signed(vm_mem[i]); p_bp_bias = $signed(vb_mem[i]); end
                    default: begin p_bp_m = $signed(om_mem[i]); p_bp_bias = $signed(ob_mem[i]); end
                endcase
            end
            @(negedge clk); p_bp_we = 0;
        end
    endtask

    initial begin
        errors = 0; got = 0;
        $readmemh("vectors/attn/x.mem", x_mem);
        $readmemh("vectors/attn/q_wgt.mem", qw_mem);
        $readmemh("vectors/attn/k_wgt.mem", kw_mem);
        $readmemh("vectors/attn/v_wgt.mem", vw_mem);
        $readmemh("vectors/attn/o_wgt.mem", ow_mem);
        $readmemh("vectors/attn/q_m.mem", qm_mem);
        $readmemh("vectors/attn/k_m.mem", km_mem);
        $readmemh("vectors/attn/v_m.mem", vm_mem);
        $readmemh("vectors/attn/o_m.mem", om_mem);
        $readmemh("vectors/attn/q_b.mem", qb_mem);
        $readmemh("vectors/attn/k_b.mem", kb_mem);
        $readmemh("vectors/attn/v_b.mem", vb_mem);
        $readmemh("vectors/attn/o_b.mem", ob_mem);
        $readmemh("vectors/attn/expect.mem", e_mem);
        $readmemh("vectors/attn/score_m.mem", sm_mem);
        m_score_v = $signed(sm_mem[0]);
        $readmemh("vectors/attn/ctx_m.mem", cm_mem);
        m_ctx_v = $signed(cm_mem[0]);
        if (x_mem[0] === 8'hxx || e_mem[0] === 32'hx) begin
            $display("FAIL: vectors missing");
            $finish;
        end

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        for (i = 0; i < TACT; i = i + 1) begin
            @(negedge clk);
            x_we = 1; x_addr = i[12:0]; x_data = x_mem[i];
        end
        @(negedge clk); x_we = 0;

        load_wgt(2'd0, NWGT);
        load_wgt(2'd1, NWGT);
        load_wgt(2'd2, NWGT);
        load_wgt(2'd3, NWGT);
        load_bp(2'd0);
        load_bp(2'd1);
        load_bp(2'd2);
        load_bp(2'd3);

        @(negedge clk); start = 1;
        timeout = 0;
        while (!done && timeout < 600000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end
        @(negedge clk);
        start = 0;

        if (!done) begin
            $display("FAIL: timeout");
            errors = errors + 1;
        end
        $display("cycles=%0d words=%0d (expect %0d)", cycle_count, got, N_WORD);

        repeat (5) @(negedge clk);
        if (got != N_WORD) begin
            $display("FAIL: word count");
            errors = errors + 1;
        end
        $display("  q_buf[0..3]     = %0d %0d %0d %0d",
                 $signed(dut.q_buf[0]), $signed(dut.q_buf[1]),
                 $signed(dut.q_buf[2]), $signed(dut.q_buf[3]));
        $display("  score_buf[0..3] = %0d %0d %0d %0d",
                 $signed(dut.score_buf[0]), $signed(dut.score_buf[1]),
                 $signed(dut.score_buf[2]), $signed(dut.score_buf[3]));
        $display("  p_buf[0..3]     = %0d %0d %0d %0d",
                 $signed(dut.p_buf[0]), $signed(dut.p_buf[1]),
                 $signed(dut.p_buf[2]), $signed(dut.p_buf[3]));
        $display("  ctx_buf[0..3]   = %0d %0d %0d %0d",
                 $signed(dut.ctx_buf[0]), $signed(dut.ctx_buf[1]),
                 $signed(dut.ctx_buf[2]), $signed(dut.ctx_buf[3]));
        for (i = 0; i < N_WORD; i = i + 1) begin
            if (cap[i] !== e_mem[i]) begin
                if (errors < 6)
                    $display("MISMATCH [%0d] got %08x exp %08x", i, cap[i], e_mem[i]);
                errors = errors + 1;
            end
        end

        if (errors == 0) $display("PASS: attention %0d words bit-exact", N_WORD);
        else $display("FAIL: %0d errors", errors);
        $finish;
    end
endmodule
