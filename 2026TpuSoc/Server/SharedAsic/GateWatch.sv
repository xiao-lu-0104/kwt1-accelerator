`timescale 1ns/1ps
// Passive observer. Do not drive the DUT, suppress failures or change sampling.
module GateWatch;
    `define GW SharedTest
    `define GN SharedTest.Cpu.u_e203_cpu.u_e203_nice_core
    `define GM SharedTest.Cpu.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.u_sirv_sim_ram.mem_r
    string History [0:23];
    integer Position = 0, Entries = 0;
    logic [17:0] ExternalAddress;
    logic ExternalRead;
    logic ExternalPending = 0;
    task automatic Record(input string Message);
        History[Position] = $sformatf("time=%0t cycle=%0d PC=%h %s", $time, `GW.Cycles, `GW.Pc, Message);
        Position = (Position + 1) % 24;
        if (Entries < 24) Entries = Entries + 1;
    endtask
    initial begin
        wait (`GW.ResetN === 1'b1);
        #1;
        $display("DIAG_START: kind=%0d layers=%0d output_words=%0d input1=%h mailbox_done=%h",
                 `GW.Kind, `GW.Layers, `GW.OutputWords, `GW.InputHost[1], `GM[2]);
    end
    always @(posedge `GW.Clock) if (`GW.ResetN) begin
        if (`GW.CommandValid && `GW.CommandReady) begin
            ExternalAddress = `GW.CommandAddress;
            ExternalRead = `GW.CommandRead;
            ExternalPending = 1;
            Record($sformatf("EXT_CMD read=%b addr=%h data=%h memory=%h",
                `GW.CommandRead, `GW.CommandAddress, `GW.CommandData, `GM[`GW.CommandAddress >> 2]));
        end
        if (`GW.ResponseValid && `GW.ResponseReady) begin
            Record($sformatf("EXT_RSP pending=%b read=%b addr=%h data=%h memory_now=%h",
                ExternalPending, ExternalRead, ExternalAddress, `GW.ResponseData, `GM[ExternalAddress >> 2]));
            ExternalPending = 0;
        end
        if (`GN.nice_req_valid && `GN.nice_req_ready)
            Record($sformatf("NICE_INST inst=%h rs1=%h rs2=%h", `GN.nice_req_inst, `GN.nice_req_rs1, `GN.nice_req_rs2));
        if (`GN.nice_icb_cmd_valid && `GN.nice_icb_cmd_ready)
            Record($sformatf("NICE_MEM read=%b addr=%h data=%h", `GN.nice_icb_cmd_read, `GN.nice_icb_cmd_addr, `GN.nice_icb_cmd_wdata));
        if (`GN.nice_icb_rsp_valid && `GN.nice_icb_rsp_ready)
            Record($sformatf("NICE_RSP data=%h error=%b", `GN.nice_icb_rsp_rdata, `GN.nice_icb_rsp_err));
    end
    final begin
        $display("DIAG_FINAL: cycle=%0d start=%0d measured=%b last_write=%0d loaded_words=%0d dma_reads=%0d dma_writes=%0d",
            `GW.Cycles, `GW.StartCycle, `GW.Measured, `GW.LastWriteCycle, `GW.LoadedWords, `GW.DmaReads, `GW.DmaWrites);
        $display("DIAG_MAILBOX: ready=%h release=%h done=%h error=%h boot=%h cause=%h mepc=%h",
            `GM[0], `GM[1], `GM[2], `GM[3], `GM[7], `GM[8], `GM[9]);
        $display("DIAG_SIGNALS: ext_valid/ready=%b%b ext_rsp_valid/ready=%b%b ext_rsp_data=%h nice_reset=%b",
            `GW.CommandValid, `GW.CommandReady, `GW.ResponseValid, `GW.ResponseReady, `GW.ResponseData, `GN.nice_rst_n);
        for (integer Index = 0; Index < Entries; Index = Index + 1)
            $display("DIAG_TRACE: %s", History[(Position - Entries + Index + 24) % 24]);
    end
    `undef GW
    `undef GN
    `undef GM
endmodule
