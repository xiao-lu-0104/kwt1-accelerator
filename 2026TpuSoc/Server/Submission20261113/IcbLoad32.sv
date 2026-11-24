// Simulation loader. Bind ONLY to the original platform loading master/port.
// Never instantiate a separate SRAM port or a new bypass interconnect for this.
module IcbLoad32 (
    input logic clk, rst_n,
    output logic cmd_valid,
    input logic cmd_ready,
    output logic [31:0] cmd_addr, cmd_wdata,
    output logic cmd_read,
    output logic [3:0] cmd_wmask,
    input logic rsp_valid,
    output logic rsp_ready,
    input logic rsp_err,
    input logic [31:0] rsp_rdata
);
    initial begin
        cmd_valid=0;cmd_addr=0;cmd_wdata=0;cmd_read=0;cmd_wmask=0;rsp_ready=0;
    end
    task automatic transfer(input logic read_access,input logic [31:0] address,
                            input logic [31:0] data,input logic [3:0] mask,
                            output logic [31:0] returned);
        integer waits;
        if (!rst_n) $fatal(1,"loader called during reset");
        @(negedge clk);
        cmd_valid=1;cmd_read=read_access;cmd_addr=address;cmd_wdata=data;cmd_wmask=mask;
        // Keep response ready low until request acceptance so a zero-wait
        // response is held by the actual target and cannot be lost.
        rsp_ready=0;waits=0;
        do begin @(posedge clk);waits++;if(waits>1000000)$fatal(1,"ICB command timeout");end while(!cmd_ready);
        @(negedge clk);cmd_valid=0;rsp_ready=1;waits=0;
        do begin @(posedge clk);waits++;if(waits>1000000)$fatal(1,"ICB response timeout");end while(!rsp_valid);
        if(rsp_err)$fatal(1,"ICB loader response error at %h",address);
        returned=rsp_rdata;
        @(negedge clk);rsp_ready=0;
    endtask
    task automatic write_word(input logic [31:0] address,data,input logic [3:0] mask);
        logic [31:0] unused;
        transfer(0,address,data,mask,unused);
    endtask
    task automatic read_word(input logic [31:0] address,output logic [31:0] data);
        transfer(1,address,0,0,data);
    endtask
endmodule
