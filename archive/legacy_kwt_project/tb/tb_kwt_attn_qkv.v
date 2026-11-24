`timescale 1ns / 1ps
module tb_kwt_attn_qkv;
    localparam TOK = 99;
    localparam D = 64;
    localparam TOTAL_ACT = TOK*D;     // 6336
    localparam TOTAL_WGT = D*D;       // 4096
    localparam N_WORD = TOK*(D/4);    // 1584

    reg clk = 0;
    reg rst_n = 0;
    reg start = 0;

    reg        q_act_we = 0;  reg [12:0] q_act_addr = 0; reg [7:0] q_act_data = 0;
    reg        q_wgt_we = 0;  reg [13:0] q_wgt_addr = 0; reg [3:0] q_wgt_data = 0;
    reg        q_bp_we = 0;   reg [7:0] q_bp_addr = 0;
    reg signed [31:0] q_bp_bias = 0; reg signed [31:0] q_bp_m = 0;
    wire q_out_we; wire [12:0] q_out_addr; wire [31:0] q_out_data;

    reg        k_act_we = 0;  reg [12:0] k_act_addr = 0; reg [7:0] k_act_data = 0;
    reg        k_wgt_we = 0;  reg [13:0] k_wgt_addr = 0; reg [3:0] k_wgt_data = 0;
    reg        k_bp_we = 0;   reg [7:0] k_bp_addr = 0;
    reg signed [31:0] k_bp_bias = 0; reg signed [31:0] k_bp_m = 0;
    wire k_out_we; wire [12:0] k_out_addr; wire [31:0] k_out_data;

    reg        v_act_we = 0;  reg [12:0] v_act_addr = 0; reg [7:0] v_act_data = 0;
    reg        v_wgt_we = 0;  reg [13:0] v_wgt_addr = 0; reg [3:0] v_wgt_data = 0;
    reg        v_bp_we = 0;   reg [7:0] v_bp_addr = 0;
    reg signed [31:0] v_bp_bias = 0; reg signed [31:0] v_bp_m = 0;
    wire v_out_we; wire [12:0] v_out_addr; wire [31:0] v_out_data;

    wire done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    kwt_attn_qkv dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .q_act_we(q_act_we), .q_act_addr(q_act_addr), .q_act_data(q_act_data), .q_act_we4(1'b0), .q_act_data32(32'd0),
        .q_wgt_we(q_wgt_we), .q_wgt_addr(q_wgt_addr), .q_wgt_data(q_wgt_data),
        .q_bp_we(q_bp_we), .q_bp_addr(q_bp_addr), .q_bp_bias(q_bp_bias), .q_bp_m(q_bp_m),
        .q_out_we(q_out_we), .q_out_addr(q_out_addr), .q_out_data(q_out_data),
        .k_act_we(k_act_we), .k_act_addr(k_act_addr), .k_act_data(k_act_data), .k_act_we4(1'b0), .k_act_data32(32'd0),
        .k_wgt_we(k_wgt_we), .k_wgt_addr(k_wgt_addr), .k_wgt_data(k_wgt_data),
        .k_bp_we(k_bp_we), .k_bp_addr(k_bp_addr), .k_bp_bias(k_bp_bias), .k_bp_m(k_bp_m),
        .k_out_we(k_out_we), .k_out_addr(k_out_addr), .k_out_data(k_out_data),
        .v_act_we(v_act_we), .v_act_addr(v_act_addr), .v_act_data(v_act_data), .v_act_we4(1'b0), .v_act_data32(32'd0),
        .v_wgt_we(v_wgt_we), .v_wgt_addr(v_wgt_addr), .v_wgt_data(v_wgt_data),
        .v_bp_we(v_bp_we), .v_bp_addr(v_bp_addr), .v_bp_bias(v_bp_bias), .v_bp_m(v_bp_m),
        .v_out_we(v_out_we), .v_out_addr(v_out_addr), .v_out_data(v_out_data),
        .done(done), .cycle_count(cycle_count)
    );

    reg [7:0]  x_mem [0:TOTAL_ACT-1];
    reg [3:0]  qw_mem [0:TOTAL_WGT-1];
    reg [3:0]  kw_mem [0:TOTAL_WGT-1];
    reg [3:0]  vw_mem [0:TOTAL_WGT-1];
    reg [31:0] qb_mem [0:D-1];
    reg [31:0] kb_mem [0:D-1];
    reg [31:0] vb_mem [0:D-1];
    reg [31:0] qm_mem [0:D-1];
    reg [31:0] km_mem [0:D-1];
    reg [31:0] vm_mem [0:D-1];
    reg [31:0] qe_mem [0:N_WORD-1];
    reg [31:0] ke_mem [0:N_WORD-1];
    reg [31:0] ve_mem [0:N_WORD-1];

    integer i, errors, q_got, k_got, v_got, timeout;
    integer qerr, kerr, verr;
    reg [31:0] q_cap [0:N_WORD-1];
    reg [31:0] k_cap [0:N_WORD-1];
    reg [31:0] v_cap [0:N_WORD-1];

    always @(negedge clk) if (q_out_we) q_got = q_got + 1;
    always @(negedge clk) if (k_out_we) k_got = k_got + 1;
    always @(negedge clk) if (v_out_we) v_got = v_got + 1;

    initial begin
        errors = 0; q_got = 0; k_got = 0; v_got = 0;

        $readmemh("vectors/qkv/x.mem", x_mem);
        $readmemh("vectors/qkv/q_wgt.mem", qw_mem);
        $readmemh("vectors/qkv/k_wgt.mem", kw_mem);
        $readmemh("vectors/qkv/v_wgt.mem", vw_mem);
        $readmemh("vectors/qkv/q_bias.mem", qb_mem);
        $readmemh("vectors/qkv/k_bias.mem", kb_mem);
        $readmemh("vectors/qkv/v_bias.mem", vb_mem);
        $readmemh("vectors/qkv/q_m.mem", qm_mem);
        $readmemh("vectors/qkv/k_m.mem", km_mem);
        $readmemh("vectors/qkv/v_m.mem", vm_mem);
        $readmemh("vectors/qkv/q_expect.mem", qe_mem);
        $readmemh("vectors/qkv/k_expect.mem", ke_mem);
        $readmemh("vectors/qkv/v_expect.mem", ve_mem);

        if (x_mem[0] === 8'hxx) begin $display("FAIL: vectors missing"); $finish; end

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        // activation into all three engines
        for (i = 0; i < TOTAL_ACT; i = i + 1) begin
            @(negedge clk);
            q_act_we = 1; q_act_addr = i[12:0]; q_act_data = x_mem[i];
            k_act_we = 1; k_act_addr = i[12:0]; k_act_data = x_mem[i];
            v_act_we = 1; v_act_addr = i[12:0]; v_act_data = x_mem[i];
        end
        @(negedge clk); q_act_we = 0; k_act_we = 0; v_act_we = 0;

        for (i = 0; i < TOTAL_WGT; i = i + 1) begin
            @(negedge clk);
            q_wgt_we = 1; q_wgt_addr = i[13:0]; q_wgt_data = qw_mem[i];
            k_wgt_we = 1; k_wgt_addr = i[13:0]; k_wgt_data = kw_mem[i];
            v_wgt_we = 1; v_wgt_addr = i[13:0]; v_wgt_data = vw_mem[i];
        end
        @(negedge clk); q_wgt_we = 0; k_wgt_we = 0; v_wgt_we = 0;

        for (i = 0; i < D; i = i + 1) begin
            @(negedge clk);
            q_bp_we = 1; q_bp_addr = i[7:0]; q_bp_bias = $signed(qb_mem[i]); q_bp_m = $signed(qm_mem[i]);
            k_bp_we = 1; k_bp_addr = i[7:0]; k_bp_bias = $signed(kb_mem[i]); k_bp_m = $signed(km_mem[i]);
            v_bp_we = 1; v_bp_addr = i[7:0]; v_bp_bias = $signed(vb_mem[i]); v_bp_m = $signed(vm_mem[i]);
        end
        @(negedge clk); q_bp_we = 0; k_bp_we = 0; v_bp_we = 0;

        @(negedge clk); start = 1;
        timeout = 0;
        while (!done && timeout < 300000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end
        @(negedge clk);

        if (!done) begin
            $display("FAIL: timeout");
            errors = errors + 1;
        end
        $display("cycles=%0d q_words=%0d k_words=%0d v_words=%0d (expect %0d each)",
                 cycle_count, q_got, k_got, v_got, N_WORD);

        if (q_got != N_WORD || k_got != N_WORD || v_got != N_WORD) begin
            $display("FAIL: output word count");
            errors = errors + 1;
        end

        repeat (5) @(negedge clk);
        qerr = 0; kerr = 0; verr = 0;
        for (i = 0; i < 3; i = i + 1)
            $display("  q_cap[%0d]=%08x  exp=%08x", i, q_cap[i], qe_mem[i]);
        for (i = 0; i < N_WORD; i = i + 1) begin
            if (q_cap[i] !== qe_mem[i]) qerr = qerr + 1;
            if (k_cap[i] !== ke_mem[i]) kerr = kerr + 1;
            if (v_cap[i] !== ve_mem[i]) verr = verr + 1;
        end
        if (qerr + kerr + verr == 0)
            $display("PASS: Q/K/V bit-exact (%0d words each)", N_WORD);
        else begin
            $display("FAIL: Q mismatches=%0d K=%0d V=%0d", qerr, kerr, verr);
            errors = errors + 1;
        end

        if (errors == 0) $display("PASS: all checks");
        else $display("FAIL: %0d errors", errors);
        $finish;
    end

    // stream capture
    always @(negedge clk) if (q_out_we) begin
        q_cap[q_out_addr] = q_out_data;
        if (q_got < 3) $display("  capture q: addr=%0d data=%08x", q_out_addr, q_out_data);
    end
    always @(negedge clk) if (k_out_we) k_cap[k_out_addr] = k_out_data;
    always @(negedge clk) if (v_out_we) v_cap[v_out_addr] = v_out_data;
endmodule
