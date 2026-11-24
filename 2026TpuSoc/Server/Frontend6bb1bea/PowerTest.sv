`timescale 1ns/1fs
// Passive golden checking. Task inputs/weights enter only through QSPI ->
// original SystemBus -> physical shared SRAM. No testbench task-load port.
module PowerTest;
    logic Clock=0, ResetN=0;
    always #3.3333335 Clock=~Clock;
    logic FlashPending=0, FlashError=0;
    logic [31:0] FlashData=0;
    wire FlashRequestValid, FlashRequestReadEnable, FlashResponseReady;
    wire [31:0] FlashRequestAddress, FlashRequestWriteData;
    SystemPhysical Dut (
        .Clock(Clock),.ResetN(ResetN),
        .FlashRequestValid(FlashRequestValid),.FlashRequestReady(!FlashPending && ResetN),
        .FlashRequestAddress(FlashRequestAddress),.FlashRequestReadEnable(FlashRequestReadEnable),
        .FlashRequestWriteData(FlashRequestWriteData),.FlashResponseValid(FlashPending),
        .FlashResponseReady(FlashResponseReady),.FlashResponseData(FlashData),.FlashResponseError(FlashError)
    );
    MemoryInit Init();
    logic [31:0] Source[0:28063];
    logic [31:0] Expected[0:12671];
    string TaskName,SourceFile,ExpectedFile,SaifFile;
    integer SourceWords,OutputWords,Fd,Word;
    longint unsigned Cycles=0,StartCycle=0,EndCycle=0;
    integer SourceReads=0,LoadedBytes=0,MatchedWords=0,ResultResponses=0;
    integer BootFetchReplies=0;
    integer SharedAccepted=0;
    bit Started=0,Stopped=0,PendingResult=0,EndRequested=0,Finish=0;
    bit SharedRead=0,DtcmRead=0,ItcmRead=0;
    realtime StartTime,EndTime;
    integer Offset;
    task automatic CheckSharedRequest(
        input logic [31:0] Address,
        input logic ReadEnable,
        input logic [3:0] WriteMask,
        input logic [31:0] WriteData
    );
        if ($isunknown(Address) || $isunknown(ReadEnable)
            || Address<32'ha0000000 || Address>=32'ha0080000)
            $fatal(1,"INVALID_SHARED_ADDRESS_OR_CONTROL addr=%h read=%b mask=%b data=%h",Address,ReadEnable,WriteMask,WriteData);
        // ICB write mask/data have no meaning for reads. A write must have
        // known data and mask; payload-specific checks below remain strict.
        if (ReadEnable===1'b0 && ($isunknown(WriteMask) || $isunknown(WriteData)))
            $fatal(1,"UNKNOWN_EFFECTIVE_SHARED_WRITE addr=%h read=%b mask=%b data=%h",Address,ReadEnable,WriteMask,WriteData);
    endtask
    initial begin
        if (!$value$plusargs("TASK=%s",TaskName) || !$value$plusargs("SOURCE=%s",SourceFile)
            || !$value$plusargs("EXPECTED=%s",ExpectedFile) || !$value$plusargs("SAIF=%s",SaifFile))
            $fatal(1,"Missing task arguments");
        if (TaskName!="ff1" && TaskName!="encoder") $fatal(1,"Bad task");
        SourceWords=TaskName=="ff1" ? 11488 : 28064;
        OutputWords=TaskName=="ff1" ? 12672 : 3168;
        $readmemh(SourceFile,Source,0,SourceWords-1);
        $readmemh(ExpectedFile,Expected,0,OutputWords-1);
        wait(Init.Done);
        repeat(30) @(negedge Clock);
        ResetN=1;
`ifndef LOCAL_POWER_TEST
        $set_toggle_region(Dut);
`endif
    end
    // Start one full cycle before the first loading-phase handshake.
    always @(negedge Clock) if (ResetN) begin
        if (!Started && Dut.SystemRequestValid && Dut.SystemRequestReady
            && !Dut.SystemRequestReadEnable && Dut.SystemRequestAddress==32'ha007ff1c
            && Dut.SystemRequestWriteData==1) begin
            Started=1;StartCycle=Cycles+1;StartTime=$realtime;
`ifndef LOCAL_POWER_TEST
            $toggle_start();
`endif
            $display("COLD_TASK_BEGIN task=%s cycle=%0d",TaskName,StartCycle);
        end
        if (EndRequested && !Stopped) begin
            EndTime=$realtime;Stopped=1;
`ifndef LOCAL_POWER_TEST
            $toggle_stop();
            $toggle_report(SaifFile,1.0e-15,"PowerTest.Dut");
`endif
            Fd=$fopen("TaskMetrics.tsv","w");
            $fdisplay(Fd,"task\t%s",TaskName);
            $fdisplay(Fd,"start_cycle\t%0d",StartCycle);
            $fdisplay(Fd,"end_cycle\t%0d",EndCycle);
            $fdisplay(Fd,"cycles\t%0d",EndCycle-StartCycle+1);
            $fdisplay(Fd,"duration_ns\t%.9f",EndTime-StartTime);
            $fdisplay(Fd,"source_bytes\t%0d",SourceReads*4);
            $fdisplay(Fd,"shared_loaded_bytes\t%0d",LoadedBytes);
            $fdisplay(Fd,"output_bytes\t%0d",MatchedWords*4);
            $fdisplay(Fd,"result_responses\t%0d",ResultResponses);
            $fdisplay(Fd,"effective_data_x_count\t0");
            $fclose(Fd);
            $display("COLD_TASK_ACTIVITY_STOP task=%s cycles=%0d duration_ns=%.9f",TaskName,EndCycle-StartCycle+1,EndTime-StartTime);
        end
        if (Finish && Stopped) begin
            $display("NEW_6BB1BEA_COLD_TASK_GOLDEN_PASS task=%s output_bytes=%0d",TaskName,MatchedWords*4);
            $finish;
        end
    end
    always @(posedge Clock) begin
        Cycles<=Cycles+1;
        if (Cycles%100000==0) $display("GATE_HEARTBEAT cycles=%0d pc=%h matched=%0d",Cycles,Dut.CpuPc,MatchedWords);
        if (Cycles>5000000) $fatal(1,"Cycle limit: CPU stuck or task incomplete pc=%h",Dut.CpuPc);
        if (ResetN) begin
            if (Dut.FetchResponseValid && Dut.FetchResponseReady && BootFetchReplies<8) begin
                $display("BOOT_FETCH_REPLY index=%0d data=%h pc=%h",BootFetchReplies,Dut.FetchResponseData,Dut.CpuPc);
                if (BootFetchReplies==0 && Dut.FetchResponseData!==64'h0000011300000093)
                    $fatal(1,"BOOT_FIRST_FETCH_MISMATCH actual=%h expected=0000011300000093",Dut.FetchResponseData);
                BootFetchReplies<=BootFetchReplies+1;
            end
            if (Dut.CpuNiceError===1'b1) $fatal(1,"NICE error");
            if ($isunknown({Dut.FetchRequestValid,Dut.ItcmRequestValid,Dut.DtcmRequestValid,Dut.SystemRequestValid,FlashRequestValid}))
                $fatal(1,"Unknown request control pc=%h",Dut.CpuPc);
            if (Dut.FetchResponseValid && Dut.FetchResponseReady && $isunknown(Dut.FetchResponseData)) $fatal(1,"Unknown instruction fetch");
            if (Dut.ItcmRequestValid && Dut.ItcmRequestReady) ItcmRead<=Dut.ItcmRequestReadEnable;
            if (Dut.DtcmRequestValid && Dut.DtcmRequestReady) DtcmRead<=Dut.DtcmRequestReadEnable;
            if (Dut.SystemRequestValid && Dut.SystemRequestReady) SharedRead<=Dut.SystemRequestReadEnable;
            if (ItcmRead && Dut.ItcmResponseValid && Dut.ItcmResponseReady && $isunknown(Dut.ItcmResponseData)) $fatal(1,"Unknown ITCM data");
            if (DtcmRead && Dut.DtcmResponseValid && Dut.DtcmResponseReady && $isunknown(Dut.DtcmResponseData)) $fatal(1,"Unknown DTCM data");
            if (SharedRead && Dut.SystemResponseValid && Dut.SystemResponseReady && $isunknown(Dut.SystemResponseData)) $fatal(1,"Unknown shared SRAM response");
            if (FlashPending && FlashResponseReady) FlashPending<=0;
            if (FlashRequestValid && !FlashPending) begin
                if ($isunknown({FlashRequestAddress,FlashRequestReadEnable}) || !FlashRequestReadEnable)
                    $fatal(1,"Invalid QSPI source transaction");
                Offset=int'(FlashRequestAddress-32'h20000000);
                FlashPending<=1;FlashError<=0;FlashData<=0;
                case (Offset)
                    'h1ff000: FlashData<=1; // exactly one cold task/layer
                    'h1ff004: FlashData<=1;
                    'h1ff008: FlashData<=1;
                    'h1ff00c: FlashData<=0; // no cross-task source prefetch
                    'h1ff010: FlashData<=1; // hardware loading through original bus
                    'h1ff014: FlashData<=1; // FF1 stream engine is part of frozen gates
                    'h1ff018: FlashData<=0; // no cross-task weight prefetch
                    default: begin
                        if (!Started || Offset<0 || Offset>=SourceWords*4 || Offset%4!=0) $fatal(1,"Out-of-window source access %h",FlashRequestAddress);
                        if ($isunknown(Source[Offset/4])) $fatal(1,"Unknown source data");
                        FlashData<=Source[Offset/4];SourceReads<=SourceReads+1;
                    end
                endcase
            end
            if (Dut.SystemRequestValid && Dut.SystemRequestReady) begin
                if (SharedAccepted<16)
                    $display("SHARED_ACCEPT cycle=%0d addr=%h read=%b mask=%b data=%h pc=%h",Cycles,Dut.SystemRequestAddress,Dut.SystemRequestReadEnable,Dut.SystemRequestWriteMask,Dut.SystemRequestWriteData,Dut.CpuPc);
                SharedAccepted<=SharedAccepted+1;
                CheckSharedRequest(Dut.SystemRequestAddress,Dut.SystemRequestReadEnable,Dut.SystemRequestWriteMask,Dut.SystemRequestWriteData);
                PendingResult<=0;
                if (!Dut.SystemRequestReadEnable) begin
                    if ($isunknown(Dut.SystemRequestWriteData)) $fatal(1,"Unknown effective SystemBus write data");
                    if (Dut.SystemRequestAddress<32'ha0060000) begin
                        if (!Started || Dut.SystemRequestWriteMask!=15) $fatal(1,"Invalid source-loading write");
                        LoadedBytes<=LoadedBytes+4;
                    end
                    if (Dut.SystemRequestAddress>=32'ha0060000 && Dut.SystemRequestAddress<32'ha007ff00) begin
                        Word=int'((Dut.SystemRequestAddress-32'ha0060000)/4);
                        if (!Started || Word!=MatchedWords || Word>=OutputWords || Dut.SystemRequestWriteMask!=15)
                            $fatal(1,"Result order/length mismatch word=%0d expected=%0d",Word,MatchedWords);
                        if (Dut.SystemRequestWriteData !== Expected[Word])
                            $fatal(1,"Golden mismatch word=%0d actual=%h expected=%h",Word,Dut.SystemRequestWriteData,Expected[Word]);
                        MatchedWords<=MatchedWords+1;PendingResult<=1;
                    end
                    if (Dut.SystemRequestAddress==32'ha007ff08) begin
                        if (Dut.SystemRequestWriteData==1) Finish<=1;
                        else if (Dut.SystemRequestWriteData!=0) $fatal(1,"Firmware failure code=%0d",Dut.SystemRequestWriteData);
                    end
                end
            end
            if (Dut.SystemResponseValid && Dut.SystemResponseReady && PendingResult) begin
                PendingResult<=0;ResultResponses<=ResultResponses+1;
                if (ResultResponses+1==OutputWords) begin
                    if (MatchedWords!=OutputWords || SourceReads*4!=SourceWords*4 || LoadedBytes!=SourceWords*4)
                        $fatal(1,"Cold-task transfer totals differ");
                    EndCycle<=Cycles+1;EndRequested<=1;
                end
            end
        end
    end
endmodule
