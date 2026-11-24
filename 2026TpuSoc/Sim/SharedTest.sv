`timescale 1ns/1ps
`include "e203_defines.v"
module SharedTest;
    `include "SharedLayout.svh"
    logic Clock = 0;
    logic ResetN = 0;
    initial forever begin #3.333 Clock = 1; #3.334 Clock = 0; end
    logic CommandValid = 0;
    logic CommandReady;
    logic [17:0] CommandAddress = 0;
    logic CommandRead = 0;
    logic [31:0] CommandData = 0;
    logic ResponseValid, ResponseReady = 0, ResponseError;
    logic [31:0] ResponseData;
    wire [31:0] Pc;
    e203_cpu_top Cpu (
        .clk(Clock), .rst_n(ResetN), .test_mode(1'b0), .inspect_pc(Pc),
        .pc_rtvec(32'h80000000), .core_mhartid(1'b0),
        .dcsr_r(32'b0), .dpc_r(32'b0), .dscratch_r(32'b0),
        .dbg_mode(1'b0), .dbg_halt_r(1'b0), .dbg_step_r(1'b0),
        .dbg_ebreakm_r(1'b0), .dbg_stopcycle(1'b0), .dbg_irq_a(1'b0),
        .ext_irq_a(1'b0), .sft_irq_a(1'b0), .tmr_irq_a(1'b0), .tcm_sd(1'b0), .tcm_ds(1'b0),
        .ext2itcm_icb_cmd_valid(1'b0), .ext2itcm_icb_cmd_addr(18'b0),
        .ext2itcm_icb_cmd_read(1'b0), .ext2itcm_icb_cmd_wdata(32'b0),
        .ext2itcm_icb_cmd_wmask(4'b0), .ext2itcm_icb_rsp_ready(1'b0),
        .ext2dtcm_icb_cmd_valid(CommandValid), .ext2dtcm_icb_cmd_ready(CommandReady),
        .ext2dtcm_icb_cmd_addr(CommandAddress), .ext2dtcm_icb_cmd_read(CommandRead),
        .ext2dtcm_icb_cmd_wdata(CommandData), .ext2dtcm_icb_cmd_wmask(4'hf),
        .ext2dtcm_icb_rsp_valid(ResponseValid), .ext2dtcm_icb_rsp_ready(ResponseReady),
        .ext2dtcm_icb_rsp_err(ResponseError), .ext2dtcm_icb_rsp_rdata(ResponseData),
        .ppi_icb_cmd_ready(1'b1), .ppi_icb_rsp_valid(1'b0), .ppi_icb_rsp_err(1'b0), .ppi_icb_rsp_rdata(32'b0),
        .plic_icb_cmd_ready(1'b1), .plic_icb_rsp_valid(1'b0), .plic_icb_rsp_err(1'b0), .plic_icb_rsp_rdata(32'b0),
        .clint_icb_cmd_ready(1'b1), .clint_icb_rsp_valid(1'b0), .clint_icb_rsp_err(1'b0), .clint_icb_rsp_rdata(32'b0),
        .fio_icb_cmd_ready(1'b1), .fio_icb_rsp_valid(1'b0), .fio_icb_rsp_err(1'b0), .fio_icb_rsp_rdata(32'b0),
        .mem_icb_cmd_ready(1'b1), .mem_icb_rsp_valid(1'b0), .mem_icb_rsp_err(1'b0), .mem_icb_rsp_rdata(32'b0)
    );
    `define ITCM Cpu.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_sirv_sim_ram.mem_r
    `define DTCM Cpu.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.u_sirv_sim_ram.mem_r
    `define NICE Cpu.u_e203_cpu.u_e203_nice_core
    longint unsigned Cycles, StartCycle = 0, LastWriteCycle;
    longint unsigned DmaReads, DmaWrites, LoadedWords = 0;
    longint unsigned Loads, Executes, Stores;
    logic LastWritePending, Measured = 0;
    integer Kind, Layers, ParameterWords, OutputWords;
    logic [31:0] InputHost [0:3167];
    logic [31:0] ParameterHost [0:298751];
    logic [31:0] ExpectedHost [0:12671];
    logic [31:0] Fractions [0:11];
    string Directory, Firmware;
    always @(posedge Clock) begin
        if (!ResetN) begin
            Cycles = 0; LastWriteCycle = 0;
            DmaReads = 0; DmaWrites = 0;
            Loads = 0; Executes = 0; Stores = 0; LastWritePending = 0;
        end else begin
            Cycles = Cycles + 1;
            if (Cpu.mem_icb_cmd_valid || Cpu.ppi_icb_cmd_valid || Cpu.fio_icb_cmd_valid)
                $fatal(1, "Unexpected CPU access outside TCM, PC=%h", Pc);
            if (`NICE.nice_req_valid && `NICE.nice_req_ready) begin
                case (`NICE.nice_req_inst[31:25])
                    0: Loads = Loads + 1;
                    1: Executes = Executes + 1;
                    2: Stores = Stores + 1;
                    default: begin end
                endcase
            end
            if (`NICE.nice_icb_cmd_valid && `NICE.nice_icb_cmd_ready) begin
                if (`NICE.nice_icb_cmd_size != 2 || `NICE.nice_icb_cmd_addr < DTCMBase
                    || `NICE.nice_icb_cmd_addr >= DTCMBase + 262144)
                    $fatal(1, "DMA escaped shared DTCM");
                if (`NICE.nice_icb_cmd_read) DmaReads = DmaReads + 1;
                else DmaWrites = DmaWrites + 1;
                LastWritePending = !`NICE.nice_icb_cmd_read
                    && `NICE.nice_icb_cmd_addr == OutputBase + 32'(OutputWords * 4 - 4);
            end
            if (`NICE.nice_icb_rsp_valid && `NICE.nice_icb_rsp_ready) begin
                if (`NICE.nice_icb_rsp_err) $fatal(1, "NICE memory bus error");
                if (LastWritePending) begin LastWriteCycle = Cycles; LastWritePending = 0; end
            end
            if (Cycles > 40000000) $fatal(1, "Shared task watchdog, PC=%h", Pc);
        end
    end

    task automatic Access(input bit Read, input logic [31:0] Address,
                          input logic [31:0] Data, output logic [31:0] Result);
        if (Address < DTCMBase || Address > DTCMBase + 262140 || Address[1:0] != 0)
            $fatal(1, "Loader address outside shared DTCM");
        @(negedge Clock);
        CommandAddress = 18'(Address - DTCMBase);
        CommandRead = Read;
        CommandData = Data;
        CommandValid = 1;
        if (!Measured && !Read && Address == InputBase) begin
            Measured = 1; StartCycle = Cycles + 1;
        end
        do @(posedge Clock); while (!CommandReady);
        @(negedge Clock);
        CommandValid = 0;
        repeat ($urandom_range(0, 2)) @(negedge Clock);
        ResponseReady = 1;
        do @(posedge Clock); while (!ResponseValid);
        if (ResponseError) $fatal(1, "Loader ICB bus error");
        Result = ResponseData;
        if (Measured && !Read) LoadedWords = LoadedWords + 1;
        @(negedge Clock);
        ResponseReady = 0;
    endtask
    task automatic Put(input logic [31:0] Address, input logic [31:0] Value);
        logic [31:0] Unused;
        Access(0, Address, Value, Unused);
    endtask
    task automatic WaitValue(input logic [31:0] Address, input logic [31:0] Value);
        logic [31:0] Result, Done;
        do begin
            Access(1, Address, 0, Result);
            Access(1, MailboxBase + 8, 0, Done);
            if (Done > 1) $fatal(1, "CPU failed/trapped: done=%0d PC=%h error=%h cause=%h mepc=%h",
                Done, Pc, `DTCM[3], `DTCM[8], `DTCM[9]);
        end while (Result != Value);
    endtask
    initial begin : Test
        logic [31:0] Result;
        longint unsigned ExpectedReads, ExpectedWrites;
        if (`E203_ITCM_ADDR_WIDTH != 18 || `E203_DTCM_ADDR_WIDTH != 18)
            $fatal(1, "Shared test requires platform 256 KiB ITCM + 256 KiB DTCM");
        if (!$value$plusargs("VECTORS=%s", Directory) || !$value$plusargs("FIRMWARE=%s", Firmware)
            || !$value$plusargs("KIND=%d", Kind) || !$value$plusargs("LAYERS=%d", Layers))
            $fatal(1, "Required plusargs: VECTORS, FIRMWARE, KIND, LAYERS");
        if (Kind < 0 || Kind > 1 || Layers < 1 || Layers > 12 || (Kind == 1 && Layers != 1))
            $fatal(1, "Invalid task mode");
        ParameterWords = Kind == 1 ? 8320 : 24896;
        OutputWords = Kind == 1 ? 12672 : 3168;
        // Only code initialization and host file I/O precede timing.
        for (int Index = 0; Index < 65536; Index++) `DTCM[Index] = 0;
        $readmemh(Firmware, `ITCM);
        $readmemh({Directory, "/Input.hex"}, InputHost);
        $readmemh({Directory, "/Fractions.hex"}, Fractions, 0, Layers-1);
        for (int Layer = 0; Layer < Layers; Layer++)
            $readmemh($sformatf("%s/Layer%0d.hex", Directory, Layer), ParameterHost,
                      Layer * ParameterWords, (Layer+1) * ParameterWords - 1);
        $readmemh($sformatf("%s/Expected%0d.hex", Directory, Layers-1), ExpectedHost, 0, OutputWords-1);
        repeat (8) @(negedge Clock);
        ResetN = 1;
        // The CPU top synchronizes reset release internally. External ICB
        // requests begin only after that reset pipeline has drained.
        repeat (8) @(negedge Clock);
        WaitValue(MailboxBase + 28, 1);
        Put(MailboxBase + 16, 32'(Kind));
        Put(MailboxBase + 20, 32'(Layers));
        // Output poison is test initialization, before input/parameter loading.
        for (int WordIndex = 0; WordIndex < OutputWords + 4; WordIndex++)
            Put(OutputBase + 32'(WordIndex * 4), 32'h5a5a5a5a);
        for (int WordIndex = 0; WordIndex < 3168; WordIndex++)
            Put(InputBase + 32'(WordIndex * 4), InputHost[WordIndex]);
        for (int Layer = 0; Layer < Layers; Layer++) begin
            for (int WordIndex = 0; WordIndex < ParameterWords; WordIndex++)
                Put(ParameterBase + 32'(WordIndex * 4), ParameterHost[Layer * ParameterWords + WordIndex]);
            Put(MailboxBase + 24, Fractions[Layer]);
            Put(MailboxBase, 32'(Layer + 1));
            WaitValue(MailboxBase + 4, 32'(Layer + 1));
            $display("PASS shared layer release %0d at cycle %0d", Layer, Cycles);
        end
        WaitValue(MailboxBase + 8, 1);
        if (!Measured || LastWriteCycle < StartCycle || LastWritePending)
            $fatal(1, "Output completion not acknowledged in measured window");
        for (int WordIndex = 0; WordIndex < OutputWords; WordIndex++) begin
            Access(1, OutputBase + 32'(WordIndex * 4), 0, Result);
            if (Result !== ExpectedHost[WordIndex])
                $fatal(1, "Shared output word %0d actual=%h expected=%h", WordIndex, Result, ExpectedHost[WordIndex]);
        end
        for (int WordIndex = 0; WordIndex < 4; WordIndex++) begin
            Access(1, OutputBase + 32'((OutputWords + WordIndex) * 4), 0, Result);
            if (Result !== 32'h5a5a5a5a) $fatal(1, "Output boundary overwritten");
        end
        ExpectedReads = Kind == 1 ? 11488 : 3168 + 24896 * 64'(Layers);
        ExpectedWrites = 64'(OutputWords);
        if (DmaReads != ExpectedReads || DmaWrites != ExpectedWrites)
            $fatal(1, "DMA traffic mismatch: read=%0d write=%0d", DmaReads, DmaWrites);
        if (Loads != (Kind == 1 ? 2 : 1 + 8 * 64'(Layers))
            || Executes != (Kind == 1 ? 99 : 10 * 64'(Layers)) || Stores != (Kind == 1 ? 99 : 1))
            $fatal(1, "Unexpected E203 command counts");
        $display("PASS SHARED: kind=%0d layers=%0d values=%0d cycles=%0d DMA_read_bytes=%0d DMA_write_bytes=%0d loaded_bytes=%0d",
            Kind, Layers, OutputWords*2, LastWriteCycle-StartCycle+1, DmaReads*4, DmaWrites*4, LoadedWords*4);
        $display("SCOPE: actual E203 CPU/LSU/TCM controllers; functional SRAM models; full platform and STA separate");
        $finish;
    end
endmodule
