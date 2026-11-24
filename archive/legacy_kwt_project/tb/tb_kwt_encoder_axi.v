`timescale 1ns / 1ps
// AXI bus functional master + REAL encoder, parameters and expected outputs.
// This validates the peripheral task; it does not instantiate an E203 CPU.
module tb_kwt_encoder_axi;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    reg axi_awvalid=0,axi_wvalid=0,axi_bready=0,axi_arvalid=0,axi_rready=0;
    wire axi_awready,axi_wready,axi_bvalid,axi_arready,axi_rvalid,axi_rlast;
    reg [31:0] axi_awaddr=0,axi_wdata=0,axi_araddr=0;
    wire [3:0] axi_awlen=0,axi_arlen=0,axi_wstrb=15,axi_awcache=0,axi_arcache=0;
    wire [2:0] axi_awsize=2,axi_arsize=2,axi_awprot=0,axi_arprot=0;
    wire [1:0] axi_awburst=1,axi_arburst=1,axi_awlock=0,axi_arlock=0;
    wire axi_wlast=1;
    wire [1:0] axi_bresp,axi_rresp;
    wire [31:0] axi_rdata;
    reg [7:0] input_bytes[0:6335],expected_bytes[0:6335];
    reg [31:0] parameter_words[0:90767];
    reg [31:0] value,expected,core_count,task_count;
    string vector_dir;
    integer i,errors=0,polls=0;
    kwt_encoder_axi_top dut(.*);
    task write_word(input [31:0] address,input [31:0] data);
        begin
            @(negedge clk);axi_awaddr=address;axi_wdata=data;axi_awvalid=1;axi_wvalid=1;
            fork
                begin @(posedge clk);while(!axi_awready) @(posedge clk);@(negedge clk);axi_awvalid=0;end
                begin @(posedge clk);while(!axi_wready) @(posedge clk);@(negedge clk);axi_wvalid=0;end
            join
            while(!axi_bvalid) @(negedge clk);
            if(axi_bresp!==0) $fatal(1,"Encoder AXI write error at %h: %b",address,axi_bresp);
            axi_bready=1;@(posedge clk);@(negedge clk);axi_bready=0;
        end
    endtask
    task read_word(input [31:0] address,output [31:0] data);
        reg [31:0] held;
        begin
            @(negedge clk);axi_araddr=address;axi_arvalid=1;
            @(posedge clk);while(!axi_arready) @(posedge clk);
            @(negedge clk);axi_arvalid=0;
            while(!axi_rvalid) @(negedge clk);
            held=axi_rdata;
            @(negedge clk);
            if(!axi_rvalid||axi_rresp!==0||!axi_rlast||axi_rdata!==held)
                $fatal(1,"Encoder AXI read/response stability error at %h",address);
            data=held;axi_rready=1;@(posedge clk);@(negedge clk);axi_rready=0;
        end
    endtask
    initial begin
        if(!$value$plusargs("VECTOR_DIR=%s",vector_dir)) vector_dir="vectors/enc12";
        $readmemh($sformatf("%s/x.mem",vector_dir),input_bytes);
        $readmemh($sformatf("%s/expect.mem",vector_dir),expected_bytes);
        $readmemh($sformatf("%s/param_stream.mem",vector_dir),parameter_words);
        if(input_bytes[0]===8'hxx || expected_bytes[6335]===8'hxx || parameter_words[90767]===32'hxxxxxxxx)
            $fatal(1,"Encoder AXI vectors missing");
        repeat(3) @(negedge clk);rst_n=1;
        read_word(32'h40000024,value);if(value!==32'h4b575431) $fatal(1,"Encoder AXI signature wrong");
        write_word(32'h40000000,2);
        for(i=0;i<1584;i=i+1)
            write_word(32'h40001000+4*i,{input_bytes[4*i+3],input_bytes[4*i+2],input_bytes[4*i+1],input_bytes[4*i]});
        write_word(32'h40000000,1);
        for(i=0;i<90768;i=i+1) begin
            write_word(32'h40000030,parameter_words[i]);
            if(i%7564==7563) $display("AXI_LAYER_PARAMETERS layer=%0d words=%0d",i/7564,i+1);
        end
        value=0;
        while(!value[1]&&polls<1000000) begin
            read_word(32'h40000004,value);polls=polls+1;
            if(value[2]) $fatal(1,"Encoder AXI task error status %h",value);
        end
        if(!value[1]||value[0]) $fatal(1,"Encoder AXI completion timeout");
        for(i=0;i<1584;i=i+1) begin
            read_word(32'h40004000+4*i,value);
            expected={expected_bytes[4*i+3],expected_bytes[4*i+2],expected_bytes[4*i+1],expected_bytes[4*i]};
            if(value!==expected) begin
                if(errors<5) $display("MISMATCH AXI output word=%0d got=%h expected=%h",i,value,expected);
                errors=errors+1;
            end
        end
        read_word(32'h40000010,value);if(value!=1584) $fatal(1,"Encoder AXI input count mismatch");
        read_word(32'h40000014,value);if(value!=90768) $fatal(1,"Encoder AXI parameter count mismatch");
        read_word(32'h40000018,value);if(value!=6336) $fatal(1,"Encoder AXI output byte count mismatch");
        read_word(32'h4000001c,value);if(value!=1584) $fatal(1,"Encoder AXI output read count mismatch");
        read_word(32'h40000008,core_count);read_word(32'h4000000c,task_count);
        repeat(10) @(negedge clk);
        read_word(32'h4000000c,value);if(value!==task_count) $fatal(1,"Encoder AXI timer still running after output readback");
        $display("AXI_MMIO inputs=1584 parameter_words=90768 output_words=1584 core_cycles=%0d peripheral_cycles=%0d",core_count,task_count);
        if(errors) $fatal(1,"Encoder AXI golden output mismatch");
        $display("PASS: encoder AXI MMIO 6336 values bit-exact / full input-parameter-output task");
        $finish;
    end
    initial begin #160000000; $fatal(1,"Encoder AXI full task timeout");end
endmodule
