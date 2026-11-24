// Passive trace at the original 32-bit System Bus. The final frontend binding
// supplies phase/last-result decodes from its real task driver/address map.
// This file neither writes memory nor bypasses the platform bus.
module IcbTaskMonitor #(
    parameter string TraceFile="BusTrace.jsonl"
) (
    input logic clk,rst_n,
    input logic task_active,caches_cleared,load_begin,
    input string task_id,
    input logic loading_transaction,result_transaction,last_result_write,
    input logic cmd_valid,cmd_ready,cmd_read,
    input logic [31:0] cmd_addr,cmd_wdata,
    input logic [3:0] cmd_wmask,
    input logic rsp_valid,rsp_ready,rsp_err
);
    integer fd;
    longint unsigned cycle=0;
    bit final_tags[64];
    integer head=0,tail=0,outstanding=0;
    bit accept_command,accept_response,tag;
    initial begin fd=$fopen(TraceFile,"w");if(!fd)$fatal(1,"trace open failed");end
    always @(posedge clk) begin
        cycle<=cycle+1;
        if(!rst_n) begin head=0;tail=0;outstanding=0;end
        else begin
            accept_command=cmd_valid && cmd_ready;
            accept_response=rsp_valid && rsp_ready;
            if(caches_cleared)
                $fdisplay(fd,"{\"task\":\"%s\",\"event\":\"task_caches_cleared\",\"cycle\":%0d}",task_id,cycle);
            if(load_begin)
                $fdisplay(fd,"{\"task\":\"%s\",\"event\":\"load_begin\",\"cycle\":%0d}",task_id,cycle);
            if(task_active && cmd_valid && cmd_ready) begin
                if($isunknown({cmd_addr,cmd_read}) || (!cmd_read && $isunknown({cmd_wmask,cmd_wdata})))$fatal(1,"accepted bus X");
                if(!cmd_read && loading_transaction)
                    $fdisplay(fd,"{\"task\":\"%s\",\"event\":\"accepted_load_write\",\"cycle\":%0d,\"interface\":\"platform_sysbus\",\"width_bits\":32,\"bytes\":%0d,\"address\":%0d,\"data\":%0d,\"mask\":%0d}",task_id,cycle,$countones(cmd_wmask),cmd_addr,cmd_wdata,cmd_wmask);
                if(!cmd_read && result_transaction)
                    $fdisplay(fd,"{\"task\":\"%s\",\"event\":\"accepted_result_write\",\"cycle\":%0d,\"interface\":\"platform_sysbus\",\"width_bits\":32,\"bytes\":%0d,\"address\":%0d,\"data\":%0d,\"mask\":%0d}",task_id,cycle,$countones(cmd_wmask),cmd_addr,cmd_wdata,cmd_wmask);
                if(last_result_write) begin
                    if(cmd_read || !result_transaction)$fatal(1,"invalid final-result decode");
                end
            end
            // Track the actual ordered command/response channel, including
            // commands outside task windows and same-cycle request/response.
            if(accept_response) begin
                if(outstanding>0) begin tag=final_tags[head];head=(head+1)%64;outstanding--;end
                else if(accept_command) begin tag=task_active && last_result_write;accept_command=0;end
                else $fatal(1,"response without accepted command");
                if(task_active && rsp_err)$fatal(1,"task response error");
                if(tag) begin
                    $fdisplay(fd,"{\"task\":\"%s\",\"event\":\"final_write_response\",\"cycle\":%0d}",task_id,cycle);
                    $fflush(fd);
                end
            end
            if(accept_command) begin
                if(outstanding>=64)$fatal(1,"monitor outstanding capacity exceeded");
                final_tags[tail]=task_active && last_result_write;
                tail=(tail+1)%64;outstanding++;
            end
        end
    end
endmodule
