`timescale 1ns/1ps
// Passive diagnostic only. The original shared SRAM fatal guard remains active.
module CpuWriteTrace;
    `define RF SharedTest.Cpu.u_e203_cpu.u_e203_core.u_e203_exu.u_e203_exu_regfile.rf_r
    `define M62 SharedTest.Cpu.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.Banks[15].Lanes[0].Macro
    logic [31:0] RecentPc[0:15]; integer Position=0,Seen=0;
    always @(posedge SharedTest.Clock) if (TaskActivity.Started && !TaskActivity.Stopped) begin
        RecentPc[Position]=SharedTest.Pc;
        Position=(Position+1)%16;
        if (Seen<16) Seen++;
    end
    final begin
        $display("CPU_WRITE_TRACE: fetch_pc=%h cycles=%0d task_started=%b task_stopped=%b",
            SharedTest.Pc,SharedTest.Cycles,TaskActivity.Started,TaskActivity.Stopped);
        $display("CPU_DTCM_WRITE: cs=%b we=%b word_address=%h byte_address=%h wem=%h din=%h",
            SharedTest.Cpu.dtcm_ram_cs,SharedTest.Cpu.dtcm_ram_we,SharedTest.Cpu.dtcm_ram_addr,
            32'h90000000+({16'b0,SharedTest.Cpu.dtcm_ram_addr}<<2),
            SharedTest.Cpu.dtcm_ram_wem,SharedTest.Cpu.dtcm_ram_din);
        $display("MACRO62_WRITE: CEN=%b GWEN=%b A=%h byte_address=%h WEN=%h D=%h Q=%h",
            `M62.CEN,`M62.GWEN,`M62.A,32'h9003c000+({20'b0,`M62.A}<<2),`M62.WEN,`M62.D,`M62.Q);
        $display("CPU_GPRS: sp=%h s0=%h s1=%h s2=%h s3=%h s4=%h s5=%h s6=%h s7=%h s8=%h s9=%h s10=%h s11=%h",
            `RF[2],`RF[8],`RF[9],`RF[18],`RF[19],`RF[20],`RF[21],`RF[22],`RF[23],`RF[24],`RF[25],`RF[26],`RF[27]);
        for (int I=0;I<Seen;I++) $display("CPU_RECENT_FETCH_PC: %h",RecentPc[(Position-Seen+I+16)%16]);
    end
    `undef RF
    `undef M62
endmodule
