`timescale 1ns/1ps
// Passive observer. The testbench calls StartWindow at the first input request
// and sets EndRequested when the final output response is accepted.
module TaskActivity;
    bit Started=0, Stopped=0, EndRequested=0;
    realtime StartTime, EndTime, WindowError;
    longint unsigned WindowCycles;
    string ActivityFile;
    initial begin
        if (!$value$plusargs("TASK_SAIF=%s",ActivityFile))
            $fatal(1,"TASK_SAIF required");
`ifndef TPU_LOCAL_WINDOW_TEST
        $set_toggle_region(SharedTest.Cpu);
`endif
    end
    task StartWindow;
        if (!TcmInitializer.Done || !TcmInitializer.Released) $fatal(1,"SYSTEM_SAIF_STARTED_DURING_INIT");
        if (Started || Stopped) $fatal(1,"Task activity window started twice");
        Started=1;
        StartTime=$realtime;
`ifndef TPU_LOCAL_WINDOW_TEST
        $toggle_start();
`endif
        $display("TASK_ACTIVITY_BEGIN: start_cycle=%0d time_ns=%0.3f",
                 SharedTest.StartCycle,StartTime);
    endtask
    initial begin
        wait (EndRequested);
        // Complete the last counted cycle at the following falling edge.
        @(negedge SharedTest.Clock);
        if (!Started || Stopped) $fatal(1,"Invalid task activity stop");
        EndTime=$realtime;
        WindowCycles=SharedTest.LastWriteCycle-SharedTest.StartCycle+1;
        WindowError=EndTime-StartTime-WindowCycles*6.667;
        if (WindowCycles==0 || WindowError>0.002 || WindowError< -0.002)
            $fatal(1,"Task SAIF window does not match complete counted cycles");
`ifndef TPU_LOCAL_WINDOW_TEST
        $toggle_stop();
        // Use picosecond SAIF units to preserve this testbench's 6.667 ns clock.
        $toggle_report(ActivityFile,1.0e-12,"SharedTest.Cpu");
`endif
        Stopped=1;
        $display("TASK_ACTIVITY_END: cycles=%0d duration_ns=%0.3f start_ns=%0.3f end_ns=%0.3f file=%s",
                 WindowCycles,EndTime-StartTime,StartTime,EndTime,ActivityFile);
    end
    final $display("TASK_ACTIVITY_FINAL: started=%b stopped=%b",Started,Stopped);
endmodule
