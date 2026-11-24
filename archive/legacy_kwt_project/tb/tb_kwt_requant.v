`timescale 1ns / 1ps
// TB: <acc_hex_32b> <m_int_hex_32b> <expected_q8_hex_2b>
module tb_kwt_requant;
    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg valid_in = 1'b0;
    reg signed [31:0] acc_in = 0;
    reg signed [31:0] m_int = 0;
    wire signed [7:0] q_out;
    wire valid_out;

    always #5 clk = ~clk;

    kwt_requant dut (
        .clk      (clk),
        .rst_n    (rst_n),
        .valid_in (valid_in),
        .acc_in   (acc_in),
        .m_int    (m_int),
        .q_out    (q_out),
        .valid_out(valid_out)
    );

    integer fd, n, i, errors;
    reg [31:0] acc_rd, m_rd;
    reg [7:0] exp_rd;

    initial begin
        errors = 0;
        fd = $fopen("vectors/requant.txt", "r");
        if (fd == 0) begin
            $display("ERROR: cannot open vectors/requant.txt");
            $finish;
        end
        if ($fscanf(fd, "%d\n", n) != 1) begin
            $display("ERROR: cannot read count");
            $finish;
        end
        $display("running %0d vectors", n);

        @(posedge clk);
        @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        for (i = 0; i < n; i = i + 1) begin
            if ($fscanf(fd, "%h %h %h\n", acc_rd, m_rd, exp_rd) != 3) begin
                $display("ERROR: fscanf failed at %0d", i);
                $finish;
            end
            @(negedge clk);
            acc_in = $signed(acc_rd);
            m_int = $signed(m_rd);
            valid_in = 1'b1;
            @(negedge clk);
            valid_in = 1'b0;
            if (!valid_out) begin
                $display("ERROR: valid_out low at %0d", i);
                errors = errors + 1;
            end else if (q_out !== $signed(exp_rd)) begin
                $display("MISMATCH[%0d]: acc=%0d m=%0d got %0d expected %0d",
                         i, acc_in, m_int, q_out, $signed(exp_rd));
                errors = errors + 1;
            end
        end

        $fclose(fd);
        if (errors == 0)
            $display("PASS: %0d/%0d vectors", n, n);
        else
            $display("FAIL: %0d errors out of %0d", errors, n);
        $finish;
    end
endmodule
