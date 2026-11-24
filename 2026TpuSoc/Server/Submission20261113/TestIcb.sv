`timescale 1ns/1ps
module TestIcb;
    logic clk=0,rst_n=0;
    always #3.333 clk=~clk;
    logic cmd_valid,cmd_ready,cmd_read,rsp_valid,rsp_ready,rsp_err;
    logic [31:0] cmd_addr,cmd_wdata,rsp_rdata;
    logic [3:0] cmd_wmask;
    logic active=0,cleared=0,begin_load=0,loading=1,result_write=0,last_write=0;
    string id="smoke";
    IcbLoad32 loader(clk,rst_n,cmd_valid,cmd_ready,cmd_addr,cmd_wdata,cmd_read,cmd_wmask,
                     rsp_valid,rsp_ready,rsp_err,rsp_rdata);
    IcbTaskMonitor #(.TraceFile("TestBusTrace.jsonl")) mon(clk,rst_n,active,cleared,begin_load,id,
        loading,result_write,last_write,cmd_valid,cmd_ready,cmd_read,cmd_addr,cmd_wdata,cmd_wmask,rsp_valid,rsp_ready,rsp_err);
    integer cycle=0,delay_count=0,accepted=0;
    logic pending=0;
    logic [31:0] memory=0,read_value=0;
    assign cmd_ready=rst_n && !pending && cycle%3!=0;
    assign rsp_valid=pending && delay_count==0;
    assign rsp_err=0;
    assign rsp_rdata=read_value;
    always @(posedge clk) begin
        cycle<=cycle+1;
        if(!rst_n) begin pending<=0;accepted<=0;end
        else begin
            if(cmd_valid && cmd_ready) begin
                accepted<=accepted+1;pending<=1;delay_count<=2;
                if(!cmd_read) begin
                    for(integer i=0;i<4;i++)if(cmd_wmask[i])memory[i*8+:8]<=cmd_wdata[i*8+:8];
                end
                read_value<=memory;
            end
            if(pending && delay_count>0)delay_count<=delay_count-1;
            if(rsp_valid && rsp_ready)pending<=0;
        end
        if(cycle>300)$fatal(1,"test timeout");
    end
    logic [31:0] value;
    initial begin
        repeat(4)@(negedge clk);rst_n=1;active=1;cleared=1;
        @(negedge clk);cleared=0;begin_load=1;
        @(negedge clk);begin_load=0;
        loader.write_word(32'ha0000000,32'h12345678,4'hf);
        loader.read_word(32'ha0000000,value);
        if(value!==32'h12345678)$fatal(1,"readback mismatch");
        loader.write_word(32'ha0000000,32'h000000ab,4'h1);
        loader.read_word(32'ha0000000,value);
        if(value!==32'h123456ab)$fatal(1,"byte mask mismatch");
        loading=0;result_write=1;last_write=1;
        loader.write_word(32'ha0060000,32'h76543210,4'hf);
        last_write=0;active=0;
        if(accepted!=5)$fatal(1,"accepted count mismatch");
        $display("ICB_LOADER_MONITOR_TEST_PASS accepted=%0d",accepted);$finish;
    end
endmodule
