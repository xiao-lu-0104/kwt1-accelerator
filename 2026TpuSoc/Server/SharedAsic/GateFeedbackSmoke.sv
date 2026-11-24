`timescale 1ns/1ps
module GateFeedbackSmoke;
    logic Clock = 0, ResetN = 0, Data = 0;
    wire Q;
    wire [3:0] Count;
    wire [3:0] NextCount = ResetN ? Count + 4'd1 : 4'b0;
    DQV0_12TR40 Hold (.CK(Clock), .D(Data), .Q(Q));
    for (genvar Bit = 0; Bit < 4; Bit++) begin : Bits
        DQV0_12TR40 Feedback (.CK(Clock), .D(NextCount[Bit]), .Q(Count[Bit]));
    end
    initial forever #5 Clock = !Clock;
    initial begin
        repeat (4) @(negedge Clock);
        #0.001;
        ResetN = 1;
        for (int Index = 1; Index <= 20; Index++) begin
            @(posedge Clock);
            #0.001;
            $display("FEEDBACK_EDGE: index=%0d count=%h next=%h Q=%b D=%b", Index, Count, NextCount, Q, Data);
            if (Count !== 4'(Index)) $fatal(1, "DFF_FEEDBACK_FAIL index=%0d count=%h", Index, Count);
            // Exercise D changes while CK is high, including a zero-delay feedback path.
            #1;
            Data = !Data;
            #0.001;
            if (Q !== !Data) $fatal(1, "DFF_HIGH_PHASE_HOLD_FAIL index=%0d Q=%b D=%b", Index, Q, Data);
        end
        $display("PASS DFF_FEEDBACK: 20 counter transitions and data changes while CK high");
        $finish;
    end
endmodule
