`timescale 1ns / 1ps
// Bit-exact TB for kwt_linear using real layer-0 FFN1 weights.
module tb_kwt_linear;
    localparam TOKENS  = 99;
    localparam IN_DIM  = 64;
    localparam OUT_DIM = 256;
    localparam TOTAL_ACT = TOKENS*IN_DIM;    // 6336
    localparam TOTAL_WGT = OUT_DIM*IN_DIM;   // 16384

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg start = 1'b0;

    reg        act_we = 0;
    reg [12:0] act_addr = 0;
    reg [7:0]  act_data = 0;

    reg        wgt_we = 0;
    reg [13:0] wgt_addr = 0;
    reg [3:0]  wgt_data = 0;

    reg        bp_we = 0;
    reg [7:0]  bp_addr = 0;
    reg signed [31:0] bp_bias = 0;
    reg signed [31:0] bp_m = 0;

    wire        out_we;
    wire [12:0] out_addr;
    wire [31:0] out_data;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    kwt_gemm_engine #(
        .IN_DIM(IN_DIM),
        .OUT_DIM(OUT_DIM),
        .TOKENS(TOKENS)
    ) dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .act_we(act_we), .act_addr(act_addr), .act_data(act_data),
        .wgt_we(wgt_we), .wgt_addr(wgt_addr), .wgt_data(wgt_data),
        .bp_we(bp_we), .bp_addr(bp_addr), .bp_bias(bp_bias), .bp_m(bp_m),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    reg [7:0]  act_mem  [0:TOTAL_ACT-1];
    reg [3:0]  wgt_mem  [0:TOTAL_WGT-1];
    reg [31:0] bias_mem [0:OUT_DIM-1];
    reg [31:0] m_mem    [0:OUT_DIM-1];
    reg [31:0] exp_mem  [0:TOTAL_ACT-1];

    integer i, got, errors, timeout;

    always @(negedge clk) begin
        if (out_we) begin
            got = got + 1;
            if (out_data !== exp_mem[out_addr]) begin
                errors = errors + 1;
                if (errors <= 10)
                    $display("MISMATCH addr=%0d got=%08x exp=%08x",
                             out_addr, out_data, exp_mem[out_addr]);
            end
        end
    end

    initial begin
        got = 0;
        errors = 0;

        $readmemh("vectors/linear/act.mem",  act_mem);
        $readmemh("vectors/linear/wgt.mem",  wgt_mem);
        $readmemh("vectors/linear/bias.mem", bias_mem);
        $readmemh("vectors/linear/m.mem",    m_mem);
        $readmemh("vectors/linear/expect.mem", exp_mem);

        repeat (2) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        $display("loading activation (%0d)", TOTAL_ACT);
        for (i = 0; i < TOTAL_ACT; i = i + 1) begin
            @(negedge clk);
            act_we = 1'b1; act_addr = i[12:0]; act_data = act_mem[i];
        end
        @(negedge clk); act_we = 1'b0;

        $display("loading weight (%0d)", TOTAL_WGT);
        for (i = 0; i < TOTAL_WGT; i = i + 1) begin
            @(negedge clk);
            wgt_we = 1'b1; wgt_addr = i[13:0]; wgt_data = wgt_mem[i];
        end
        @(negedge clk); wgt_we = 1'b0;

        $display("loading bias/multiplier (%0d)", OUT_DIM);
        for (i = 0; i < OUT_DIM; i = i + 1) begin
            @(negedge clk);
            bp_we = 1'b1; bp_addr = i[7:0];
            bp_bias = $signed(bias_mem[i]);
            bp_m    = $signed(m_mem[i]);
        end
        @(negedge clk); bp_we = 1'b0;

        $display("start");
        @(negedge clk); start = 1'b1;

        timeout = 0;
        while (!done && timeout < 200000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end

        @(negedge clk);
        if (!done) begin
            $display("FAIL: timeout after %0d cycles", timeout);
        end else begin
            $display("done. cycles=%0d  outputs=%0d/%0d  errors=%0d",
                     cycle_count, got, TOTAL_ACT, errors);
            if (errors == 0 && got == TOTAL_ACT)
                $display("PASS: %0d/%0d words bit-exact", got, TOTAL_ACT);
            else
                $display("FAIL: %0d outputs, %0d mismatches", got, errors);
        end
        $finish;
    end

    initial begin
        #20_000_000;
        $display("FAIL: global timeout");
        $finish;
    end
endmodule
