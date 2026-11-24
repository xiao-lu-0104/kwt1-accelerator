`timescale 1ns / 1ps
// AXI4-Lite slave smoke test: write CTRL, stream MFCC words, read back
// STATUS / PRED / CYCLES and the activation window.
module tb_kwt_axi_slave;

    reg         aclk = 0;
    reg         aresetn = 0;

    reg  [15:0] awaddr = 0;
    reg         awvalid = 0;
    wire        awready;
    reg  [31:0] wdata = 0;
    reg  [3:0]  wstrb = 4'hF;
    reg         wvalid = 0;
    wire        wready;
    wire [1:0]  bresp;
    wire        bvalid;
    reg         bready = 1;
    reg  [15:0] araddr = 0;
    reg         arvalid = 0;
    wire        arready;
    wire [31:0] rdata;
    wire [1:0]  rresp;
    wire        rvalid;
    reg         rready = 1;

    wire        start;
    wire        soft_rst;
    reg         busy = 0;
    reg         done_in = 0;
    reg  [3:0]  pred = 4'd11;
    reg  [31:0] cycles = 32'h0012_3456;

    wire [9:0]  mfcc_addr;
    wire [31:0] mfcc_data;
    wire        mfcc_we;
    wire [10:0] frame_count;

    wire [9:0]  act_rd_addr;
    wire [31:0] act_rd_data = {act_rd_addr, 22'd0};

    integer errors = 0;
    integer i;
    reg [31:0] rd;

    // start must have pulsed high at least once
    reg saw_start = 0;
    always @(posedge aclk) if (start) saw_start <= 1'b1;

    always #5 aclk = ~aclk;

    kwt_axi_slave dut (
        .aclk(aclk), .aresetn(aresetn),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .start(start), .soft_rst(soft_rst),
        .busy(busy), .done_in(done_in), .pred(pred), .cycles(cycles),
        .mfcc_addr(mfcc_addr), .mfcc_data(mfcc_data), .mfcc_we(mfcc_we),
        .frame_count(frame_count),
        .act_rd_addr(act_rd_addr), .act_rd_data(act_rd_data)
    );

    // capture MFCC writes
    reg [31:0] cap [0:1023];
    always @(posedge aclk) if (mfcc_we) cap[mfcc_addr] <= mfcc_data;

    task axi_write(input [15:0] a, input [31:0] d);
        begin
            @(negedge aclk);
            awaddr = a; awvalid = 1; wdata = d; wvalid = 1;
            @(posedge aclk);
            while (!awready) @(posedge aclk);
            @(negedge aclk);
            awvalid = 0;
            while (!wready) @(posedge aclk);
            @(negedge aclk);
            wvalid = 0;
            while (!bvalid) @(posedge aclk);
            @(negedge aclk);
        end
    endtask

    task axi_read(input [15:0] a, output [31:0] d);
        begin
            @(negedge aclk);
            araddr = a; arvalid = 1;
            @(posedge aclk);
            while (!arready) @(posedge aclk);
            @(negedge aclk);
            arvalid = 0;
            while (!rvalid) @(posedge aclk);
            d = rdata;
            @(negedge aclk);
        end
    endtask

    initial begin
        repeat (4) @(posedge aclk);
        aresetn = 1;
        repeat (2) @(posedge aclk);

        // ---- write MFCC words ----
        for (i = 0; i < 8; i = i + 1)
            axi_write(16'h0100 + i * 4, 32'hA0B0_C000 + i);

        if (frame_count !== 11'd8) begin
            $display("FAIL: frame_count=%0d expect 8", frame_count);
            errors = errors + 1;
        end
        for (i = 0; i < 8; i = i + 1) begin
            if (cap[i] !== (32'hA0B0_C000 + i)) begin
                $display("FAIL: mfcc[%0d]=%08x", i, cap[i]);
                errors = errors + 1;
            end
        end

        // ---- read STATUS / PRED / CYCLES ----
        axi_read(16'h0004, rd);
        if (rd !== 32'd0) begin
            $display("FAIL: status=%08x expect 0", rd);
            errors = errors + 1;
        end
        busy = 1;
        axi_read(16'h0004, rd);
        if (rd !== 32'd1) begin
            $display("FAIL: status busy=%08x expect 1", rd);
            errors = errors + 1;
        end
        busy = 0; done_in = 1;
        axi_read(16'h0004, rd);
        if (rd !== 32'd2) begin
            $display("FAIL: status done=%08x expect 2", rd);
            errors = errors + 1;
        end

        axi_read(16'h0008, rd);
        if (rd !== 32'd11) begin
            $display("FAIL: pred=%08x expect 11", rd);
            errors = errors + 1;
        end

        axi_read(16'h000C, rd);
        if (rd !== 32'h0012_3456) begin
            $display("FAIL: cycles=%08x", rd);
            errors = errors + 1;
        end

        axi_read(16'h0010, rd);
        if (rd !== 32'd8) begin
            $display("FAIL: nframes=%08x expect 8", rd);
            errors = errors + 1;
        end

        // ---- activation window read ----
        // act_rd_addr = araddr[11:2], so 0x800 + 5*4 selects index 0x205
        axi_read(16'h0800 + 5 * 4, rd);
        if (rd !== {10'h205, 22'd0}) begin
            $display("FAIL: act[5]=%08x expect %08x", rd, {10'h205, 22'd0});
            errors = errors + 1;
        end

        // ---- start pulse ----
        axi_write(16'h0000, 32'h0000_0001);
        repeat (2) @(posedge aclk);

        if (!saw_start) begin
            $display("FAIL: start never asserted");
            errors = errors + 1;
        end

        if (errors == 0) $display("PASS: AXI4-Lite slave, all registers behave");
        else             $display("FAIL: %0d errors", errors);
        $finish;
    end

endmodule
