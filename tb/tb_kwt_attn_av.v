`timescale 1ns / 1ps
module tb_kwt_attn_av;
    localparam TOK = 99;
    localparam D = 64;
    localparam N_P = TOK*TOK;      // 9801
    localparam N_V = TOK*D;        // 6336
    localparam N_WORD = TOK*(D/4); // 1584

    reg clk = 0;
    reg rst_n = 0;
    reg start = 0;

    wire [13:0] p_rd_addr;
    wire [12:0] v_rd_addr;
    reg  [31:0] p_rd_data4;
    reg  [31:0] v_rd_data4;

    reg        m_we = 0;
    reg signed [31:0] m_data = 0;

    wire        out_we;
    wire [12:0] out_addr;
    wire [31:0] out_data;
    wire        done;
    wire [31:0] cycle_count;

    always #5 clk = ~clk;

    reg [7:0]  p_mem [0:N_P+3];
    reg [7:0]  v_mem [0:N_V+195];
    reg [31:0] m_mem [0:0];
    reg [31:0] e_mem [0:N_WORD-1];
    reg [31:0] cap   [0:N_WORD-1];
    reg signed [31:0] acc_cap  [0:N_WORD-1];
    reg signed [31:0] acc1_cap [0:N_WORD-1];
    reg signed [31:0] acc2_cap [0:N_WORD-1];
    reg signed [31:0] acc3_cap [0:N_WORD-1];

    always @(*) begin
        p_rd_data4 = {p_mem[p_rd_addr + 14'd3], p_mem[p_rd_addr + 14'd2],
                      p_mem[p_rd_addr + 14'd1], p_mem[p_rd_addr]};
        v_rd_data4 = {v_mem[v_rd_addr + 13'd192], v_mem[v_rd_addr + 13'd128],
                      v_mem[v_rd_addr + 13'd64],  v_mem[v_rd_addr]};
    end

    kwt_attn_av dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .p_rd_addr(p_rd_addr), .p_rd_data4(p_rd_data4),
        .v_rd_addr(v_rd_addr), .v_rd_data4(v_rd_data4),
        .m_we(m_we), .m_data(m_data),
        .out_we(out_we), .out_addr(out_addr), .out_data(out_data),
        .done(done), .cycle_count(cycle_count)
    );

    integer i, errors, timeout, got;

    always @(negedge clk) if (out_we) begin
        cap[out_addr] = out_data;
        acc_cap[out_addr]  = dut.u_engine.acc0;
        acc1_cap[out_addr] = dut.u_engine.acc1;
        acc2_cap[out_addr] = dut.u_engine.acc2;
        acc3_cap[out_addr] = dut.u_engine.acc3;
        got = got + 1;
    end

    // trace V loader row switches

    initial begin
        errors = 0; got = 0;
        $readmemh("vectors/av/p.mem", p_mem);
        $readmemh("vectors/av/v.mem", v_mem);
        $readmemh("vectors/av/m.mem", m_mem);
        $readmemh("vectors/av/expect.mem", e_mem);
        if (p_mem[0] === 8'hxx || e_mem[0] === 32'hx) begin
            $display("FAIL: vectors missing");
            $finish;
        end

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        @(negedge clk);
        m_we = 1; m_data = $signed(m_mem[0]);
        @(negedge clk);
        m_we = 0;

        @(negedge clk); start = 1;
        timeout = 0;
        while (!done && timeout < 400000) begin
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
        $display("DBG wgt[0]=%02x wgt[2944]=%02x wgt[3072]=%02x wgt[8191]=%02x",
                 dut.u_engine.wgt_buf[0], dut.u_engine.wgt_buf[2944],
                 dut.u_engine.wgt_buf[3072], dut.u_engine.wgt_buf[8191]);
        $display("DBG wg24=%02x/%02x wg25=%02x wg26=%02x wg27=%02x wg6hdr=%02x %02x %02x %02x",
                 dut.u_engine.wgt_buf[24*128], dut.u_engine.wgt_buf[24*128+127],
                 dut.u_engine.wgt_buf[25*128], dut.u_engine.wgt_buf[26*128],
                 dut.u_engine.wgt_buf[27*128],
                 dut.u_engine.wgt_buf[6*128], dut.u_engine.wgt_buf[7*128],
                 dut.u_engine.wgt_buf[8*128], dut.u_engine.wgt_buf[9*128]);
        $display("DBG act[0]=%02x act[96]=%02x act[12671]=%02x",
                 dut.u_engine.act_buf[0], dut.u_engine.act_buf[96],
                 dut.u_engine.act_buf[12671]);
        $display("DBG m[0]=%0d m[23]=%0d m[24]=%0d m[63]=%0d bias[24]=%0d",
                 dut.u_engine.m_buf[0], dut.u_engine.m_buf[23],
                 dut.u_engine.m_buf[24], dut.u_engine.m_buf[63],
                 dut.u_engine.bias_buf[24]);
        $display("DBG act t0[0..7]=%02x %02x %02x %02x %02x %02x %02x %02x",
                 dut.u_engine.act_buf[0], dut.u_engine.act_buf[1],
                 dut.u_engine.act_buf[2], dut.u_engine.act_buf[3],
                 dut.u_engine.act_buf[4], dut.u_engine.act_buf[5],
                 dut.u_engine.act_buf[6], dut.u_engine.act_buf[7]);

        repeat (5) @(negedge clk);
        if (got != N_WORD) begin
            $display("FAIL: word count");
            errors = errors + 1;
        end
        for (i = 0; i < N_WORD; i = i + 1) begin
            if (cap[i] !== e_mem[i]) begin
                if (errors < 30)
                    $display("MISMATCH [%0d] tok=%0d grp=%0d got %08x exp %08x",
                             i, i/16, i%16, cap[i], e_mem[i]);
                errors = errors + 1;
            end
        end

        if (errors == 0) $display("PASS: ctx %0d words bit-exact", N_WORD);
        else $display("FAIL: %0d errors", errors);
        $finish;
    end
endmodule
