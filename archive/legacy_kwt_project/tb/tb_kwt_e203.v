`timescale 1ns/1ps
`include "e203_defines.v"
`include "kwt_e203_images.vh"
// Real platform CPU + ICB/AXI bridge + real encoder. Only initial TCM preload
// and final RAM inspection are performed by the testbench; no MMIO bus master.
module tb_kwt_e203;
    reg clk,lfextclk,rst_n;
    // Match the platform ISA harness: an NBA X->0 reset transition at time 0
    // lets every asynchronous AON reset process observe the initial assertion.
    initial begin clk<=0;lfextclk<=0;rst_n<=0;end
    always begin #3.333 clk=1;#3.334 clk=0;end
    always #33 lfextclk=~lfextclk;
    `define KWT_CPU u_e203_soc_top.u_e203_subsys_top.u_e203_subsys_main.u_e203_cpu_top
    `define KWT_ITCM `KWT_CPU.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_sirv_sim_ram
    `define KWT_DTCM `KWT_CPU.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.u_sirv_sim_ram
    `define KWT_EXU `KWT_CPU.u_e203_cpu.u_e203_core.u_e203_exu
    `define KWT_DEVICE u_e203_soc_top.u_e203_subsys_top.u_e203_subsys_main.u_e203_subsys_mems.u_perips_expl_axi_slv
    reg [7:0] itcm_image[0:`KWT_TCM_BYTES-1],dtcm_image[0:`KWT_TCM_BYTES-1];
    reg [7:0] golden[0:6335];
    string image_dir,vector_dir;
    integer i,j,smoke=0,errors=0;
    integer root_cycles=0,instructions=0,input_beats=0,param_beats=0,output_beats=0;
    localparam MAILBOX_WORD=(`KWT_MAILBOX-32'h90000000)/4;
    localparam OUTPUT_WORD=(`KWT_OUTPUT_BUFFER-32'h90000000)/4;
    wire [31:0] magic=`KWT_DTCM.mem_r[MAILBOX_WORD];
    function [31:0] mailbox(input integer index);
        mailbox=`KWT_DTCM.mem_r[MAILBOX_WORD+index];
    endfunction
    always @(posedge clk) if(rst_n) root_cycles<=root_cycles+1;
`ifdef KWT_CPU_TRACE
    initial begin
        #17000;
        $display("CPU_TRACE pc=%h corerst=%b hfclkrst=%b wdg_irq=%b rtc_irq=%b instructions=%0d",
            `KWT_EXU.u_e203_exu_commit.alu_cmt_i_pc,u_e203_soc_top.u_e203_subsys_top.corerst,
            u_e203_soc_top.u_e203_subsys_top.hfclkrst,
            u_e203_soc_top.u_e203_subsys_top.aon_wdg_irq_a,
            u_e203_soc_top.u_e203_subsys_top.aon_rtc_irq_a,instructions);
    end
`endif
    always @(posedge `KWT_CPU.clk) begin
        if(`KWT_EXU.u_e203_exu_commit.alu_cmt_i_valid&&`KWT_EXU.u_e203_exu_commit.alu_cmt_i_ready)
            instructions<=instructions+1;
    end
    always @(posedge `KWT_DEVICE.clk) begin
        if(`KWT_DEVICE.u_mmio.x_we && `KWT_DEVICE.u_mmio.input_lane==3) input_beats<=input_beats+1;
        if(`KWT_DEVICE.axi_wvalid&&`KWT_DEVICE.axi_wready&&`KWT_DEVICE.u_mmio.enabled_param) begin
            param_beats<=param_beats+1;
            if(param_beats%7564==7563) $display("CPU_LAYER_PARAMETERS layer=%0d words=%0d",param_beats/7564,param_beats+1);
        end
        if(`KWT_DEVICE.axi_rvalid&&`KWT_DEVICE.axi_rready&&`KWT_DEVICE.u_mmio.reading_output&&`KWT_DEVICE.axi_rresp==0)
            output_beats<=output_beats+1;
    end
    initial begin
        if(`E203_ITCM_RAM_DW!=64 || `E203_DTCM_RAM_DW!=32 ||
           `E203_ITCM_RAM_DP*8!=`KWT_TCM_BYTES || `E203_DTCM_RAM_DP*4!=`KWT_TCM_BYTES)
            $fatal(1,"CPU image requires existing 256 KiB ITCM and DTCM, 64/32-bit storage words");
        if(!$value$plusargs("IMAGE_DIR=%s",image_dir)) image_dir="images/full";
        if(!$value$plusargs("VECTOR_DIR=%s",vector_dir)) vector_dir="vectors/enc12";
        if($value$plusargs("SMOKE=%d",smoke)) begin end
        $readmemh($sformatf("%s/itcm.mem",image_dir),itcm_image);
        $readmemh($sformatf("%s/dtcm.mem",image_dir),dtcm_image);
        $readmemh($sformatf("%s/expect.mem",vector_dir),golden);
        if(itcm_image[0]===8'hxx || dtcm_image[`KWT_TCM_BYTES-1]===8'hxx || golden[6335]===8'hxx)
            $fatal(1,"CPU image/vector file missing");
        for(i=0;i<`E203_ITCM_RAM_DP;i=i+1)
            for(j=0;j<8;j=j+1) `KWT_ITCM.mem_r[i][8*j +: 8]=itcm_image[8*i+j];
        for(i=0;i<`E203_DTCM_RAM_DP;i=i+1)
            for(j=0;j<4;j=j+1) `KWT_DTCM.mem_r[i][8*j +: 8]=dtcm_image[4*i+j];
        repeat(30) @(negedge clk);rst_n=1;
        $display("CPU_BOOT: preload complete; real E203 instruction execution; smoke=%0d",smoke);
        wait(magic==32'h4b57544f || magic==32'h4b575446 || magic==32'h4b575454);
        repeat(8) @(negedge clk);
        if(magic==32'h4b575454)
            $fatal(1,"CPU trap: mcause=%h mepc=%h mtval=%h",mailbox(7),mailbox(8),mailbox(9));
        if(magic!=32'h4b57544f || mailbox(1)!=0)
            $fatal(1,"CPU application failed: magic=%h result=%h",magic,mailbox(1));
        if(instructions<20) $fatal(1,"CPU completion without sufficient committed instructions");
        if(smoke) begin
            if(input_beats!=1||param_beats!=0||output_beats!=0) $fatal(1,"CPU smoke transfer count mismatch");
            $display("CPU_SMOKE instructions=%0d input_words=%0d",instructions,input_beats);
            $display("PASS: E203 CPU boot / C program / ICB-AXI MMIO / input / reset");
        end else begin
            for(i=0;i<6336;i=i+1) begin
                if(((`KWT_DTCM.mem_r[OUTPUT_WORD+i/4]>>(8*(i%4)))&255)!=={24'd0,golden[i]}) begin
                    if(errors<5) $display("MISMATCH CPU shared output byte=%0d got_word=%h expected=%h",i,`KWT_DTCM.mem_r[OUTPUT_WORD+i/4],golden[i]);
                    errors=errors+1;
                end
            end
            if(input_beats!=1584 || param_beats!=90768 || output_beats!=1584)
                $fatal(1,"CPU transfer counts input=%0d parameters=%0d output=%0d",input_beats,param_beats,output_beats);
            if(mailbox(6)!=1 || {mailbox(5),mailbox(4)}==0 || mailbox(2)==0 || mailbox(3)==0)
                $fatal(1,"CPU/core/peripheral cycle measurements missing");
            $display("CPU_TASK inputs=%0d parameter_words=%0d output_words=%0d core_cycles=%0d peripheral_cycles=%0d cpu_cycles=%0d instructions=%0d",input_beats,param_beats,output_beats,mailbox(2),mailbox(3),{mailbox(5),mailbox(4)},instructions);
            if(errors) $fatal(1,"CPU shared-memory output mismatches=%0d",errors);
            $display("PASS: E203 CPU C driver full encoder / 6336 shared-memory bytes bit-exact");
        end
        $finish;
    end
    initial begin
        repeat(40000000) @(posedge clk);
        $fatal(1,"CPU task timeout pc=%h mailbox=%h root_cycles=%0d",`KWT_EXU.u_e203_exu_commit.alu_cmt_i_pc,magic,root_cycles);
    end
    e203_soc_top u_e203_soc_top(
        .hfextclk(clk),.hfxoscen(),.lfextclk(lfextclk),.lfxoscen(),
        .io_pads_jtag_TCK_i_ival(1'b0),.io_pads_jtag_TDI_i_ival(1'b0),
        .io_pads_jtag_TMS_i_ival(1'b0),.io_pads_jtag_TDO_o_oval(),.io_pads_jtag_TDO_o_oe(),
        .io_pads_gpioA_i_ival(32'd0),.io_pads_gpioA_o_oval(),.io_pads_gpioA_o_oe(),
        .io_pads_gpioB_i_ival(32'd0),.io_pads_gpioB_o_oval(),.io_pads_gpioB_o_oe(),
        .io_pads_qspi0_sck_o_oval(),.io_pads_qspi0_cs_0_o_oval(),
        .io_pads_qspi0_dq_0_i_ival(1'b1),.io_pads_qspi0_dq_0_o_oval(),.io_pads_qspi0_dq_0_o_oe(),
        .io_pads_qspi0_dq_1_i_ival(1'b1),.io_pads_qspi0_dq_1_o_oval(),.io_pads_qspi0_dq_1_o_oe(),
        .io_pads_qspi0_dq_2_i_ival(1'b1),.io_pads_qspi0_dq_2_o_oval(),.io_pads_qspi0_dq_2_o_oe(),
        .io_pads_qspi0_dq_3_i_ival(1'b1),.io_pads_qspi0_dq_3_o_oval(),.io_pads_qspi0_dq_3_o_oe(),
        .io_pads_aon_erst_n_i_ival(rst_n),.io_pads_aon_pmu_dwakeup_n_i_ival(1'b1),
        .io_pads_aon_pmu_vddpaden_o_oval(),.io_pads_aon_pmu_padrst_o_oval(),
        .io_pads_bootrom_n_i_ival(1'b0),.io_pads_dbgmode0_n_i_ival(1'b1),
        .io_pads_dbgmode1_n_i_ival(1'b1),.io_pads_dbgmode2_n_i_ival(1'b1));
endmodule
