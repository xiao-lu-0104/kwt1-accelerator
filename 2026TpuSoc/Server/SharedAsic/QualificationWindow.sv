`timescale 1ns/1ps
// Match original observation boundaries without collecting a second power SAIF.
module TaskActivity;
    bit Started=0, Stopped=0, EndRequested=0;
    realtime StartTime, Error;
    longint unsigned Cycles;
    task StartWindow;
        if (Started || Stopped) $fatal(1,"QUALIFICATION_WINDOW_RESTART");
        Started=1; StartTime=$realtime;
    endtask
    initial begin
        wait(EndRequested);
        @(negedge SharedTest.Clock);
        Cycles=SharedTest.LastWriteCycle-SharedTest.StartCycle+1;
        Error=$realtime-StartTime-Cycles*6.667;
        if (!Started || Cycles==0 || Error>0.002 || Error < -0.002)
            $fatal(1,"QUALIFICATION_WINDOW_MISMATCH");
        Stopped=1;
    end
endmodule
