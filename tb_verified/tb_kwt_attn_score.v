`timescale 1ns / 1ps
module tb_kwt_attn_score;
    localparam TOK = 99;
    localparam D = 64;
    localparam TOTAL_ACT = TOK*D;     // 6336
    localparam GROUPS = 25;
    localparam N_WORD = TOK*GROUPS;   // 2475

    reg clk = 0;
    reg rst_n = 0;
    reg start = 0;

    wire [12:0] q_rd_addr;
    wire [12:0] k_rd_addr;
    reg  [31:0] q_rd_data4;
    reg  [31:0] k_rd_data4;

    reg        m_we = 0;
    reg signed [31:0] m_data = 0;

    wire        out_we;
    wire [12:0] out_addr;
    wire [63:0] out_data;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    reg [7:0]  q_mem [0:TOTAL_ACT-1];
    reg [7:0]  k_mem [0:TOTAL_ACT+3];
    reg [31:0] m_mem [0:0];
    reg [63:0] e_mem [0:N_WORD-1];
    reg [63:0] cap   [0:N_WORD-1];

    // combinational sources
    always @(*) begin
        q_rd_data4 = {q_mem[q_rd_addr + 13'd3], q_mem[q_rd_addr + 13'd2],
                      q_mem[q_rd_addr + 13'd1], q_mem[q_rd_addr]};
        k_rd_data4 = {k_mem[k_rd_addr + 13'd3], k_mem[k_rd_addr + 13'd2],
                      k_mem[k_rd_addr + 13'd1], k_mem[k_rd_addr]};
    end

    kwt_attn_score dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .q_rd_addr(q_rd_addr), .q_rd_data4(q_rd_data4),
        .k_rd_addr(k_rd_addr), .k_rd_data4(k_rd_data4),
        .m_we(m_we), .m_data(m_data),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    integer i, errors, timeout, got;

    always @(negedge clk) if (out_we) begin
        cap[out_addr] = out_data;
        got = got + 1;
    end

    initial begin
        errors = 0; got = 0;
        $readmemh("vectors/score/q.mem", q_mem);
        $readmemh("vectors/score/k.mem", k_mem);
        $readmemh("vectors/score/m.mem", m_mem);
        $readmemh("vectors/score/expect.mem", e_mem);
        if (q_mem[0] === 8'hxx || e_mem[0] === 64'hx) begin
            $display("FAIL: vectors missing");
            $finish;
        end

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        @(negedge clk);
        m_we = 1;
        m_data = $signed(m_mem[0]);
        @(negedge clk);
        m_we = 0;

        @(negedge clk); start = 1;
        timeout = 0;
        while (!done && timeout < 200000) begin
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
        for (i = 0; i < N_WORD; i = i + 1) begin
            if (cap[i] !== e_mem[i]) begin
                if (errors < 6)
                    $display("MISMATCH [%0d] got %016x exp %016x", i, cap[i], e_mem[i]);
                errors = errors + 1;
            end
        end

        if (errors == 0) $display("PASS: score %0d words bit-exact", N_WORD);
        else $display("FAIL: %0d errors", errors);
        $finish;
    end
endmodule
