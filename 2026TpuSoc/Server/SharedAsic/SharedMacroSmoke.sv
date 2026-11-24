`timescale 1ns/1ps
// Isolated raw-macro contract test. This does not replace platform TCM arrays.
module SharedMacroSmoke;
    logic Clock=0, CEN=1, GWEN=1;
    logic [15:0] WEN=16'hffff, D=0;
    logic [11:0] A=0;
    wire [15:0] Q;
    logic [15:0] Expected, Held;
    integer Checks=0;
    RAMSP4096X16 Macro (
        .Q(Q), .CLK(Clock), .CEN(CEN), .GWEN(GWEN), .WEN(WEN),
        .A(A), .D(D), .EMA(3'd2), .EMAW(2'd0), .RET1N(1'b1)
    );
    always #3.3335 Clock=~Clock;
    task Write(input logic [11:0] Address, input logic [15:0] Value, Mask);
        @(negedge Clock); A=Address; D=Value; WEN=Mask; CEN=0; GWEN=0;
        @(posedge Clock); #1;
    endtask
    task ReadCheck(input logic [11:0] Address, input logic [15:0] Value);
        @(negedge Clock); A=Address; CEN=0; GWEN=1; WEN=16'hffff;
        @(posedge Clock); #1;
        if (Q !== Value) $fatal(1,"SHARED_MACRO_READ address=%h actual=%h expected=%h",Address,Q,Value);
        Checks++;
    endtask
    initial begin
        Write(12'h000,16'h55aa,16'h0000);
        Write(12'hfff,16'hc33c,16'h0000);
        Write(12'h001,16'h1234,16'h0000);
        Write(12'h801,16'h9876,16'h0000);
        ReadCheck(12'h000,16'h55aa); ReadCheck(12'hfff,16'hc33c);
        ReadCheck(12'h001,16'h1234); ReadCheck(12'h801,16'h9876);
        Expected=16'h55aa;
        for (int Bit=0; Bit<16; Bit++) begin
            Expected[Bit]=~Expected[Bit];
            Write(12'h000,Expected,~(16'h0001<<Bit));
            ReadCheck(12'h000,Expected);
        end
        Write(12'h000,~Expected,16'hffff);
        ReadCheck(12'h000,Expected);
        Held=Q;
        @(negedge Clock); CEN=1; GWEN=0; WEN=0; A=0; D=~Expected;
        repeat(2) begin
            @(posedge Clock); #1;
            if (Q !== Held) $fatal(1,"SHARED_MACRO_DISABLED_OUTPUT_HOLD");
        end
        ReadCheck(12'h000,Expected);
        ReadCheck(12'hfff,16'hc33c);
        $display("PASS SHARED_MACRO_SMOKE: checks=%0d; all 16 active-low WEN bits; disabled CEN hold; synchronous read; zero-delay functional model only",Checks);
        $finish;
    end
endmodule
