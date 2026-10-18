`timescale 1ns / 1ps
module tb_kwt_softmax;
    localparam N = 99;
    localparam CASES = 60;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg start = 1'b0;
    reg        s_we = 0;
    reg [6:0]  s_addr = 0;
    reg signed [15:0] s_data = 0;

    wire        out_we;
    wire [6:0]  out_addr;
    wire [7:0]  out_data;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    kwt_softmax #(.N(N)) dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .s_we(s_we), .s_addr(s_addr), .s_data(s_data),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    reg [15:0] score_mem [0:CASES*N-1];
    reg [7:0]  exp_mem   [0:CASES*N-1];

    integer c, i, errors, got, timeout;
    reg [7:0] got_vec [0:N-1];

    always @(negedge clk) begin
        if (out_we) begin
            got_vec[out_addr] = out_data;
            got = got + 1;
        end
    end

    initial begin
        errors = 0;
        $readmemh("vectors/softmax/score.mem", score_mem);
        $readmemh("vectors/softmax/expect.mem", exp_mem);

        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        for (c = 0; c < CASES; c = c + 1) begin
            // load scores
            for (i = 0; i < N; i = i + 1) begin
                @(negedge clk);
                s_we = 1'b1; s_addr = i[6:0]; s_data = score_mem[c*N + i];
            end
            @(negedge clk); s_we = 1'b0;

            got = 0;
            @(negedge clk); start = 1'b1;

            timeout = 0;
            while (!done && timeout < 5000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (!done) begin
                $display("FAIL case %0d: timeout", c);
                errors = errors + 1;
            end
            @(negedge clk);
            start = 1'b0;
            @(negedge clk);

            if (got != N) begin
                $display("FAIL case %0d: got %0d outputs", c, got);
                errors = errors + 1;
            end else begin
                for (i = 0; i < N; i = i + 1) begin
                    if (got_vec[i] !== exp_mem[c*N + i]) begin
                        if (errors < 10)
                            $display("MISMATCH case %0d idx %0d: got %0d exp %0d",
                                     c, i, got_vec[i], exp_mem[c*N + i]);
                        errors = errors + 1;
                    end
                end
            end
        end

        if (errors == 0)
            $display("PASS: %0d cases x %0d values bit-exact", CASES, N);
        else
            $display("FAIL: %0d mismatches", errors);
        $finish;
    end
endmodule
