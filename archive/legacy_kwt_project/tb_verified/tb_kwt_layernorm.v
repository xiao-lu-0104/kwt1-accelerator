`timescale 1ns / 1ps
module tb_kwt_layernorm;
    localparam N = 64;
    localparam ROWS = 20;
    localparam TOTAL = N*ROWS;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg start = 1'b0;

    reg        in_we = 0;
    reg [12:0] in_addr = 0;
    reg signed [15:0] in_data = 0;

    reg        gp_we = 0;
    reg [5:0]  gp_addr = 0;
    reg signed [15:0] gp_gamma = 0;
    reg signed [15:0] gp_beta = 0;
    reg [31:0] eps_q = 0;

    wire        out_we;
    wire [12:0] out_addr;
    wire signed [7:0] out_data;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    kwt_layernorm #(.N(N), .ROWS(ROWS)) dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .in_we(in_we), .in_addr(in_addr), .in_data(in_data),
        .gp_we(gp_we), .gp_addr(gp_addr), .gp_gamma(gp_gamma), .gp_beta(gp_beta),
        .eps_q(eps_q),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    reg [15:0] x_mem [0:TOTAL-1];
    reg [15:0] g_mem [0:N-1];
    reg [15:0] b_mem [0:N-1];
    reg [7:0]  e_mem [0:TOTAL-1];
    reg [7:0]  got_vec [0:TOTAL-1];

    integer i, errors, got, timeout;

    always @(negedge clk) begin
        if (out_we) begin
            got_vec[out_addr] = out_data;
            got = got + 1;
        end
    end

    initial begin
        errors = 0;
        $readmemh("vectors/ln/x.mem", x_mem);
        $readmemh("vectors/ln/gamma.mem", g_mem);
        $readmemh("vectors/ln/beta.mem", b_mem);
        $readmemh("vectors/ln/expect.mem", e_mem);
        if (x_mem[0] === 16'hxxxx || e_mem[0] === 8'hxx) begin
            $display("FAIL: vector files missing or unreadable");
            $finish;
        end

        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        for (i = 0; i < N; i = i + 1) begin
            @(negedge clk);
            gp_we = 1; gp_addr = i[5:0];
            gp_gamma = $signed(g_mem[i]);
            gp_beta  = $signed(b_mem[i]);
        end
        @(negedge clk); gp_we = 0;

        for (i = 0; i < TOTAL; i = i + 1) begin
            @(negedge clk);
            in_we = 1; in_addr = i[12:0]; in_data = $signed(x_mem[i]);
        end
        @(negedge clk); in_we = 0;

        got = 0;
        @(negedge clk); start = 1;
        timeout = 0;
        while (!done && timeout < 200000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end
        @(negedge clk);
        if (!done) begin
            $display("FAIL: timeout");
            errors = errors + 1;
        end else begin
            $display("done. cycles=%0d outputs=%0d/%0d", cycle_count, got, TOTAL);
            if (got != TOTAL) begin
                $display("FAIL: output count");
                errors = errors + 1;
            end else begin
                for (i = 0; i < TOTAL; i = i + 1) begin
                    if (got_vec[i] !== e_mem[i]) begin
                        if (errors < 10)
                            $display("MISMATCH [%0d] got %0d exp %0d", i, got_vec[i], e_mem[i]);
                        errors = errors + 1;
                    end
                end
            end
        end

        if (errors == 0) $display("PASS: %0d values bit-exact", TOTAL);
        else $display("FAIL: %0d mismatches", errors);
        $finish;
    end
endmodule
