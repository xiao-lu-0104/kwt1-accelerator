`timescale 1ns/1ps
module SaifSmokeDut(input Clock,ResetN,output [3:0] Count);
    wire [3:0] NextCount = ResetN ? Count+4'd1 : 4'd0;
    for (genvar Bit=0;Bit<4;Bit++) begin : Bits
        DQV0_12TR40 F(.CK(Clock),.D(NextCount[Bit]),.Q(Count[Bit]));
    end
endmodule
module SaifSmoke;
    logic Clock=0,ResetN=0;
    wire [3:0] Count;
    SaifSmokeDut Dut(Clock,ResetN,Count);
    initial forever #5 Clock=!Clock;
    initial begin
        $set_toggle_region(SaifSmoke.Dut);
        repeat(4) @(negedge Clock);
        if (Count !== 4'b0000) $fatal(1,"SAIF_SMOKE_RESET");
        ResetN=1;
        $toggle_start();
        repeat(32) @(negedge Clock);
        $toggle_stop();
        if (Count !== 4'b0000) $fatal(1,"SAIF_SMOKE_COUNTER");
        $toggle_report("smoke.saif",1.0e-9,"SaifSmoke.Dut");
        $display("PASS SAIF_SMOKE: 32 active counter cycles, 320 ns; actual DQV0 library model");
        $finish;
    end
endmodule
