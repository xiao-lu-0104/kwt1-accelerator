`timescale 1ns / 1ps
// TB: <act 128 hex> <wgt 1024 hex> <acc0 8 hex> <acc1 8 hex> <acc2 8 hex> <acc3 8 hex>
module tb_kwt_gemm4;
    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg valid_in = 1'b0;
    reg [64*8-1:0] act_flat = 0;
    reg [4*64*4-1:0] wgt_flat = 0;
    wire signed [31:0] acc0, acc1, acc2, acc3;
    wire valid_out;

    always #5 clk = ~clk;

    kwt_gemm4 dut (
        .clk(clk), .rst_n(rst_n), .valid_in(valid_in),
        .act_flat(act_flat), .wgt_flat(wgt_flat),
        .acc_in0(32'sd0), .acc_in1(32'sd0), .acc_in2(32'sd0), .acc_in3(32'sd0),
        .acc0(acc0), .acc1(acc1), .acc2(acc2), .acc3(acc3),
        .valid_out(valid_out)
    );

    integer fd, n, i, errors;
    reg [64*8-1:0] a_rd;
    reg [4*64*4-1:0] w_rd;
    reg [31:0] e0, e1, e2, e3;

    initial begin
        errors = 0;
        fd = $fopen("vectors/gemm4.txt", "r");
        if (fd == 0) begin
            $display("ERROR: cannot open vectors/gemm4.txt");
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
            if ($fscanf(fd, "%h %h %h %h %h %h\n", a_rd, w_rd, e0, e1, e2, e3) != 6) begin
                $display("ERROR: fscanf failed at %0d", i);
                $finish;
            end
            @(negedge clk);
            act_flat = a_rd;
            wgt_flat = w_rd;
            valid_in = 1'b1;
            @(negedge clk);
            valid_in = 1'b0;
            if (!valid_out) begin
                $display("ERROR: valid_out low at %0d", i);
                errors = errors + 1;
            end else begin
                if (acc0 !== $signed(e0)) begin
                    $display("MISMATCH[%0d] ch0: got %0d exp %0d", i, acc0, $signed(e0));
                    errors = errors + 1;
                end
                if (acc1 !== $signed(e1)) begin
                    $display("MISMATCH[%0d] ch1: got %0d exp %0d", i, acc1, $signed(e1));
                    errors = errors + 1;
                end
                if (acc2 !== $signed(e2)) begin
                    $display("MISMATCH[%0d] ch2: got %0d exp %0d", i, acc2, $signed(e2));
                    errors = errors + 1;
                end
                if (acc3 !== $signed(e3)) begin
                    $display("MISMATCH[%0d] ch3: got %0d exp %0d", i, acc3, $signed(e3));
                    errors = errors + 1;
                end
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
