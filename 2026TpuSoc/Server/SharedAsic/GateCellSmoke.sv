`timescale 1ns/1ps
module GateCellSmoke;
    logic Clock = 0, Data = 0;
    wire Q;
    logic Previous = 0;
    DQV0_12TR40 Cell (.CK(Clock), .D(Data), .Q(Q));
    initial forever #5 Clock = !Clock;
    initial begin
        repeat (2) @(posedge Clock);
        for (int Index = 0; Index < 16; Index++) begin
            @(negedge Clock);
            #0.001;
            Data = 1'(Index ^ (Index >> 1));
            #1;
            if (Q !== Previous) $fatal(1, "DFF_SMOKE_CHANGED_WITHOUT_POSEDGE index=%0d", Index);
            @(posedge Clock);
            #0.001;
            if (Q !== Data) $fatal(1, "DFF_SMOKE_FAIL index=%0d D=%b Q=%b", Index, Data, Q);
            Previous = Data;
        end
        $display("PASS DFF_SMOKE: actual DQV0 model, 16 sampled cycles");
        $finish;
    end
endmodule
