`timescale 1ns/1ps
// Local fixture for the actual passive TaskActivity observer, without VCS SAIF.
module LocalTaskPowerTop;
    SharedTest SharedTest();
    TaskActivity TaskActivity();
endmodule
module SharedTest;
    logic Clock=0;
    longint unsigned Cycles=0,StartCycle=0,LastWriteCycle=0;
    initial forever begin #3.333 Clock=1; #3.334 Clock=0; end
    always @(posedge Clock) Cycles=Cycles+1;
    initial begin
        repeat(4) @(negedge Clock);
        StartCycle=Cycles+1;
        TaskActivity.StartWindow();
        // Three counted cycles, the last ends with an accepted output response.
        repeat(3) @(posedge Clock);
        #0.001;
        LastWriteCycle=Cycles;
        TaskActivity.EndRequested=1;
        @(negedge Clock); #0.002;
        if (!TaskActivity.Stopped || TaskActivity.WindowCycles!=3
            || TaskActivity.WindowError>0.002 || TaskActivity.WindowError< -0.002)
            $fatal(1,"Passive window is not three complete cycles");
        $display("PASS LOCAL_TASK_WINDOW: start request through final response; three complete cycles");
        $finish;
    end
endmodule
