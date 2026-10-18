`timescale 1ns / 1ps
module tb_kwt_gelu;
    reg clk = 0;
    reg rst_n = 0;
    reg valid_in = 0;
    reg signed [7:0] x_in = 0;
    wire signed [7:0] y_out;
    wire valid_out;

    always #5 clk = ~clk;

    kwt_gelu dut (
        .clk(clk), .rst_n(rst_n), .valid_in(valid_in),
        .x_in(x_in), .y_out(y_out), .valid_out(valid_out)
    );

    reg [7:0] x_mem [0:255];
    reg [7:0] e_mem [0:255];
    integer i, errors;

    initial begin
        errors = 0;
        $readmemh("vectors/gelu/x.mem", x_mem);
        $readmemh("vectors/gelu/expect.mem", e_mem);
        if (x_mem[0] === 8'hxx || e_mem[0] === 8'hxx) begin
            $display("FAIL: vector files missing");
            $finish;
        end

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        for (i = 0; i < 256; i = i + 1) begin
            @(negedge clk);
            x_in = $signed(x_mem[i]);
            valid_in = 1;
            @(negedge clk);
            valid_in = 0;
            if (!valid_out) begin
                $display("ERROR: valid low at %0d", i);
                errors = errors + 1;
            end else if (y_out !== $signed(e_mem[i])) begin
                $display("MISMATCH x=%0d got %0d exp %0d", $signed(x_mem[i]), y_out, $signed(e_mem[i]));
                errors = errors + 1;
            end
        end

        if (errors == 0) $display("PASS: 256/256 GELU values bit-exact");
        else $display("FAIL: %0d mismatches", errors);
        $finish;
    end
endmodule
