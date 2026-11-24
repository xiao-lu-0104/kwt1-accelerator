`timescale 1ns / 1ps
// Bus-protocol/backend test. Synthetic core events, real output SRAM wrapper.
// A separate full-core test checks numerical inference over this same bus.
module tb_kwt_encoder_mmio;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    reg axi_awvalid=0,axi_wvalid=0,axi_bready=0,axi_arvalid=0,axi_rready=0;
    wire axi_awready,axi_wready,axi_bvalid,axi_arready,axi_rvalid,axi_rlast;
    reg [31:0] axi_awaddr=0,axi_wdata=0,axi_araddr=0;
    reg [3:0] axi_awlen=0,axi_arlen=0,axi_wstrb=15;
    reg [2:0] axi_awsize=2,axi_arsize=2;
    reg [1:0] axi_awburst=1,axi_arburst=1,axi_awlock=0,axi_arlock=0;
    reg axi_wlast=1;
    wire [1:0] axi_bresp,axi_rresp;
    wire [31:0] axi_rdata;
    wire core_rst_n,core_start,x_we,param_valid;
    wire [12:0] x_addr;
    wire [7:0] x_data;
    wire [63:0] param_data;
    reg param_ready=0,core_out_we=0,core_done=0;
    reg [12:0] core_out_addr=0;
    reg [7:0] core_out_data=0;
    reg [31:0] core_cycles=32'h1234;
    wire [3:0] cur_layer=3,ld_sel=6;
    wire [13:0] ld_addr=17;
    integer inputs=0,records=0,starts=0,round=0,i;
    reg [31:0] value,first_time;
    kwt_encoder_mmio #(.INPUT_BYTES(16),.PARAM_WORDS(8)) dut(.*);
    always @(posedge clk or negedge core_rst_n) begin
        if(!core_rst_n) begin inputs<=0;records<=0;starts<=0;end
        else begin
            if(x_we) begin
                if(x_addr!==inputs || x_data!==((round*64+inputs)&255))
                    $fatal(1,"MMIO input byte/address mismatch index=%0d addr=%0d data=%h",inputs,x_addr,x_data);
                inputs<=inputs+1;
            end
            if(core_start) starts<=starts+1;
            if(param_valid&&param_ready) begin
                if(param_data!=={32'h100+2*records+1,32'h100+2*records})
                    $fatal(1,"MMIO parameter record mismatch %0d: %h",records,param_data);
                records<=records+1;
            end
        end
    end
    task write_word(input [31:0] address,input [31:0] data,input [3:0] enables,
                    input integer aw_delay,input integer w_delay,input [1:0] response);
        reg [1:0] held;
        begin
            fork
                begin
                    repeat(aw_delay+1) @(negedge clk);
                    axi_awaddr=address;axi_awvalid=1;
                    @(posedge clk);while(!axi_awready) @(posedge clk);
                    @(negedge clk);axi_awvalid=0;
                end
                begin
                    repeat(w_delay+1) @(negedge clk);
                    axi_wdata=data;axi_wstrb=enables;axi_wvalid=1;
                    @(posedge clk);while(!axi_wready) @(posedge clk);
                    @(negedge clk);axi_wvalid=0;
                end
            join
            while(!axi_bvalid) @(negedge clk);
            held=axi_bresp;
            repeat(2) begin @(negedge clk);if(!axi_bvalid||axi_bresp!==held) $fatal(1,"B response changed under backpressure");end
            if(held!==response) $fatal(1,"Write %h got response %b expected %b",address,held,response);
            axi_bready=1;@(posedge clk);@(negedge clk);axi_bready=0;
        end
    endtask
    task read_word(input [31:0] address,input [1:0] response,output [31:0] data);
        reg [31:0] held;
        begin
            @(negedge clk);axi_araddr=address;axi_arvalid=1;
            @(posedge clk);while(!axi_arready) @(posedge clk);
            @(negedge clk);axi_arvalid=0;
            while(!axi_rvalid) @(negedge clk);
            held=axi_rdata;
            repeat(3) begin
                @(negedge clk);
                if(!axi_rvalid || axi_rdata!==held || axi_rresp!==response || !axi_rlast)
                    $fatal(1,"Read %h response/hold/RLAST failure: data=%h resp=%b",address,axi_rdata,axi_rresp);
            end
            data=held;axi_rready=1;@(posedge clk);@(negedge clk);axi_rready=0;
        end
    endtask
    task reset_task;
        begin write_word(32'h40000000,2,15,0,0,0);repeat(2) @(negedge clk);end
    endtask
    task fill_input;
        integer n;
        reg [31:0] word_data;
        begin
            for(n=0;n<4;n=n+1) begin
                word_data=((round*64+n*4)&255)|(((round*64+n*4+1)&255)<<8)|
                          (((round*64+n*4+2)&255)<<16)|(((round*64+n*4+3)&255)<<24);
                write_word(32'h40001000+4*n,word_data,15,n%3,(n+1)%3,0);
            end
            if(inputs!=16) $fatal(1,"Input serializer did not drain before B response");
        end
    endtask
    task produce_output;
        integer n;
        begin
            for(n=0;n<16;n=n+1) begin
                @(negedge clk);core_out_we=1;core_out_addr=n;core_out_data=(round*64+n)^8'h5a;
            end
            @(negedge clk);core_out_we=0;
            repeat(2) @(negedge clk);core_cycles=32'h1234;core_done=1;
            @(negedge clk);core_done=0;core_cycles=32'h5678;
        end
    endtask
    initial begin
        repeat(3) @(negedge clk);rst_n=1;
        read_word(32'h40000024,0,value);if(value!==32'h4b575431) $fatal(1,"Bad peripheral signature");
        read_word(32'h40010024,3,value);
        read_word(32'h40000025,2,value);
        write_word(32'h40010000,0,15,0,0,3);
        write_word(32'h40001001,0,15,0,0,2);
        axi_awsize=1;write_word(32'h40001000,0,15,0,0,2);axi_awsize=2;
        axi_awlock=1;write_word(32'h40001000,0,15,0,0,2);axi_awlock=0;
        axi_wlast=0;write_word(32'h40001000,0,15,0,0,2);axi_wlast=1;
        write_word(32'h40000000,1,15,0,0,2);
        write_word(32'h40000030,0,15,0,0,2);
        write_word(32'h40001004,0,15,0,0,2);
        write_word(32'h40001000,0,1,0,0,2);
        write_word(32'h40001000,0,0,0,0,0);
        read_word(32'h40000010,0,value);if(value!=0) $fatal(1,"Rejected writes changed input count");
        // Drain unsupported write/read bursts, with no task side effects.
        @(negedge clk);axi_awlen=2;axi_awaddr=32'h40001000;axi_awvalid=1;
        @(posedge clk);while(!axi_awready) @(posedge clk);
        @(negedge clk);axi_awvalid=0;
        for(i=0;i<3;i=i+1) begin
            axi_wvalid=1;axi_wlast=(i==2);axi_wdata=0;axi_wstrb=15;
            @(posedge clk);while(!axi_wready) @(posedge clk);
            @(negedge clk);
        end
        axi_wvalid=0;axi_wlast=1;axi_awlen=0;
        if(!axi_bvalid||axi_bresp!=2) $fatal(1,"Unsupported burst write did not error");
        axi_bready=1;@(posedge clk);@(negedge clk);axi_bready=0;
        axi_arlen=2;axi_araddr=32'h40000024;axi_arvalid=1;
        @(posedge clk);while(!axi_arready) @(posedge clk);
        @(negedge clk);axi_arvalid=0;axi_rready=1;
        for(i=0;i<3;i=i+1) begin
            @(posedge clk);
            if(!axi_rvalid||axi_rresp!=2||axi_rlast!=(i==2)) $fatal(1,"Unsupported burst read count/RLAST failure");
        end
        @(negedge clk);axi_rready=0;axi_arlen=0;
        if(inputs!=0) $fatal(1,"Unsupported burst wrote core input");
        // Keep a response pending while reset is attempted on the write channel.
        @(negedge clk);axi_araddr=32'h40000024;axi_arvalid=1;
        @(posedge clk);while(!axi_arready) @(posedge clk);
        @(negedge clk);axi_arvalid=0;
        while(!axi_rvalid) @(negedge clk);
        write_word(32'h40000000,2,15,0,0,2);
        if(!axi_rvalid || axi_rdata!==32'h4b575431 || axi_rresp!==0 || !core_rst_n)
            $fatal(1,"Rejected reset invalidated an outstanding read");
        axi_rready=1;@(posedge clk);@(negedge clk);axi_rready=0;
        for(round=0;round<2;round=round+1) begin
            reset_task;param_ready=0;fill_input;
            write_word(32'h40000000,1,15,0,1,0);
            write_word(32'h40000000,1,15,0,0,2);
            write_word(32'h40001000,0,15,0,0,2);
            read_word(32'h40004000,2,value);
            write_word(32'h40000030,32'h100,15,0,0,0);
            write_word(32'h40000030,32'h101,15,0,0,0);
            fork
                write_word(32'h40000030,32'h102,15,0,0,0);
                begin
                    repeat(5) @(negedge clk);
                    read_word(32'h40000004,0,value);
                    if(!value[0]||value[3]) $fatal(1,"Status did not report blocked parameter FIFO");
                    @(negedge clk);param_ready=1;
                end
            join
            for(i=3;i<8;i=i+1) write_word(32'h40000030,32'h100+i,15,i%2,(i+1)%2,0);
            repeat(3) @(negedge clk);
            if(records!=4||starts!=1) $fatal(1,"Core did not accept exactly one task and four records");
            produce_output;
            read_word(32'h40000004,0,value);
            if(value[2:0]!==3'b010) $fatal(1,"Bad completion status %h",value);
            read_word(32'h40000008,0,value);if(value!==32'h1234) $fatal(1,"Core cycle snapshot changed after completion");
            read_word(32'h40004004,2,value);
            for(i=0;i<4;i=i+1) begin
                read_word(32'h40004000+4*i,0,value);
                if(value!==((((round*64+i*4)^8'h5a)&255)|((((round*64+i*4+1)^8'h5a)&255)<<8)|
                    ((((round*64+i*4+2)^8'h5a)&255)<<16)|((((round*64+i*4+3)^8'h5a)&255)<<24)))
                    $fatal(1,"Output packing/address mismatch %0d: %h",i,value);
            end
            read_word(32'h4000001c,0,value);if(value!=4) $fatal(1,"Output read count wrong");
            read_word(32'h4000000c,0,first_time);repeat(8) @(negedge clk);
            read_word(32'h4000000c,0,value);if(value!=first_time||value==0) $fatal(1,"Task diagnostic timer did not freeze");
            write_word(32'h40000030,0,15,0,0,2);
        end
        // Abort with a half-written parameter record, then verify invalidation.
        reset_task;round=0;fill_input;write_word(32'h40000000,1,15,0,0,0);
        write_word(32'h40000030,32'h100,15,0,0,0);reset_task;
        read_word(32'h40000014,0,value);if(value!=0||param_valid) $fatal(1,"Reset retained parameter data/count");
        read_word(32'h40004000,2,value);
        $display("PASS: encoder MMIO channel ordering / backpressure / errors / bursts / two tasks / reset / output SRAM");
        $finish;
    end
    initial begin #500000; $fatal(1,"MMIO protocol test timeout");end
endmodule
