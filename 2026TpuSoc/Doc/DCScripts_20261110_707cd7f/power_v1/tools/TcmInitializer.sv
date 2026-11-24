`timescale 1ns/1ps
// Simulation loader only. All writes/readback use real SRAM wrapper ports while
// external reset is asserted; every force is released before CPU startup.
module TcmInitializer;
    `define TI SharedTest.Cpu.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram
    `define TD SharedTest.Cpu.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram
    logic [63:0] FirmwareWords[0:32767];
    string Firmware;
    logic [14:0] IAddress=0;
    logic [15:0] DAddress=0;
    logic [63:0] IData=0;
    logic IEnable=0,DEnable=0,Write=0;
    bit Done=0,Released=0;
    integer CodeWrites=0,DataWrites=0,CodeReads=0,DataReads=0;
    initial begin
        if (!$value$plusargs("FIRMWARE=%s",Firmware)) $fatal(1,"TCM_INIT_FIRMWARE_REQUIRED");
        $readmemh(Firmware,FirmwareWords);
        for (int I=0;I<32768;I++) if ($isunknown(FirmwareWords[I])) $fatal(1,"TCM_INIT_INCOMPLETE_FIRMWARE %0d",I);
        if (SharedTest.ResetN!==1'b0) $fatal(1,"TCM_INIT_REQUIRES_EXTERNAL_RESET");
        force `TI.cs=IEnable; force `TD.cs=DEnable;
        force `TI.we=Write; force `TD.we=Write;
        force `TI.addr=IAddress; force `TD.addr=DAddress;
        force `TI.wem=8'hff; force `TD.wem=4'hf;
        force `TI.din=IData; force `TD.din=32'b0;
        for (int I=0;I<65536;I++) begin
            @(negedge SharedTest.Clock);
            Write=1; DEnable=1; DAddress=16'(I);
            IEnable=I<32768; IAddress=15'(I); IData=FirmwareWords[I%32768];
            @(posedge SharedTest.Clock); #0.001;
            DataWrites++; if (IEnable) CodeWrites++;
        end
        // Full-capacity readback verifies every initialized word via real Q.
        for (int I=0;I<65536;I++) begin
            @(negedge SharedTest.Clock);
            Write=0; DEnable=1; DAddress=16'(I);
            IEnable=I<32768; IAddress=15'(I);
            @(posedge SharedTest.Clock); #0.001;
            if (`TD.dout!==32'b0) $fatal(1,"TCM_INIT_DTCM_READBACK %0d %h",I,`TD.dout);
            DataReads++;
            if (IEnable) begin
                if (`TI.dout!==FirmwareWords[I]) $fatal(1,"TCM_INIT_ITCM_READBACK %0d actual=%h expected=%h",I,`TI.dout,FirmwareWords[I]);
                CodeReads++;
            end
        end
        @(negedge SharedTest.Clock); IEnable=0; DEnable=0; Write=0;
        release `TI.cs; release `TD.cs;
        release `TI.we; release `TD.we;
        release `TI.addr; release `TD.addr;
        release `TI.wem; release `TD.wem;
        release `TI.din; release `TD.din;
        Released=1;
        if (SharedTest.ResetN!==1'b0) $fatal(1,"TCM_INIT_RESET_RELEASED_EARLY");
        Done=1;
        $display("PASS PHYSICAL_TCM_INIT: ITCM_writes=%0d DTCM_writes=%0d ITCM_readback=%0d DTCM_readback=%0d; all loader forces released before CPU reset release",CodeWrites,DataWrites,CodeReads,DataReads);
    end
    always @(posedge SharedTest.ResetN) if (!Done || !Released) $fatal(1,"CPU_STARTED_BEFORE_TCM_INIT_RELEASE");
    final $display("PHYSICAL_TCM_INIT_FINAL: done=%b released=%b",Done,Released);
    `undef TI
    `undef TD
endmodule
