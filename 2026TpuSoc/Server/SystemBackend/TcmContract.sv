`timescale 1ns/1ps
module TcmPortContract #(parameter DW=64,MW=8,AW=15,DP=32768)(output bit Done=0);
    logic Clock=0,Cs=0,We=0;
    logic [AW-1:0] Address=0;
    logic [DW-1:0] Data=0;
    logic [MW-1:0] Mask=0;
    wire [DW-1:0] Actual,Reference;
    logic [DW-1:0] Expected;
    integer Checks=0;
    sirv_gnrl_ram #(.DW(DW),.MW(MW),.AW(AW),.DP(DP),.FORCE_X2ZERO(0)) Dut(
        .sd(1'b0),.ds(1'b0),.ls(1'b0),.rst_n(1'b1),.clk(Clock),
        .cs(Cs),.we(We),.addr(Address),.din(Data),.wem(Mask),.dout(Actual));
    sirv_sim_ram #(.DW(DW),.MW(MW),.AW(AW),.DP(DP),.FORCE_X2ZERO(0)) Original(
        .clk(Clock),.cs(Cs),.we(We),.addr(Address),.din(Data),.wem(Mask),.dout(Reference));
    always #3.3335 Clock=~Clock;
    task Write(input logic [AW-1:0] A,input logic [DW-1:0] D,input logic [MW-1:0] M);
        @(negedge Clock); Cs=1; We=1; Address=A; Data=D; Mask=M;
        @(posedge Clock); #1;
    endtask
    task Read(input logic [AW-1:0] A,input logic [DW-1:0] E);
        @(negedge Clock); Cs=1; We=0; Address=A; Mask=0;
        @(posedge Clock); #1;
        if (Actual!==E || Reference!==E)
            $fatal(1,"TCM_READ_CONTRACT DW=%0d address=%h actual=%h original=%h expected=%h",DW,A,Actual,Reference,E);
        Checks++;
    endtask
    function automatic logic [DW-1:0] Pattern(input int Bank,input int Edge);
        logic [63:0] Value;
        Value=64'hd39a_1275_6bc4_e801 ^ (64'(Bank)*64'h0102_0408_1020_4081) ^ 64'(Edge);
        return DW'(Value);
    endfunction
    initial begin
        // Initialize only the words being tested through legal macro writes.
        for (int Bank=0;Bank<DP/4096;Bank++) begin
            Write(AW'(Bank*4096),Pattern(Bank,0),'1);
            Write(AW'(Bank*4096+4095),Pattern(Bank,1),'1);
        end
        for (int Bank=DP/4096-1;Bank>=0;Bank--) begin
            Read(AW'(Bank*4096),Pattern(Bank,0));
            Read(AW'(Bank*4096+4095),Pattern(Bank,1));
        end
        for (int Bank=0;Bank<DP/4096;Bank++) begin
            Expected=Pattern(Bank,0);
            for (int Byte=0;Byte<MW;Byte++) begin
                Expected[8*Byte+:8]=~Expected[8*Byte+:8];
                Write(AW'(Bank*4096),Expected,MW'(1)<<Byte);
                Read(AW'(Bank*4096),Expected);
            end
            Write(AW'(Bank*4096),~Expected,'0);
            Read(AW'(Bank*4096),Expected);
            @(negedge Clock); Cs=0; We=1; Address=AW'(Bank*4096); Data=~Expected; Mask='1;
            repeat(2) @(posedge Clock);
            Read(AW'(Bank*4096),Expected);
        end
        @(negedge Clock); Cs=0;
        Done=1;
        $display("PASS TCM_PORT_CONTRACT: DW=%0d DP=%0d banks=%0d macros=%0d checks=%0d; byte masks, bank selection, disabled writes and valid-read latency match original RAM; zero-delay only",DW,DP,DP/4096,(DP/4096)*(DW/16),Checks);
    end
endmodule
module TcmContract;
    wire ItcmDone,DtcmDone;
    TcmPortContract #(.DW(64),.MW(8),.AW(15),.DP(32768)) Itcm(ItcmDone);
    TcmPortContract #(.DW(32),.MW(4),.AW(16),.DP(65536)) Dtcm(DtcmDone);
    initial begin
        wait(ItcmDone && DtcmDone);
        $display("PASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros; full CPU binding functional test still pending");
        $finish;
    end
endmodule
