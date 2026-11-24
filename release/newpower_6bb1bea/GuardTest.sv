`timescale 1ns/1ps
module GuardTest;
integer CaseId;
    task automatic CheckSharedRequest(
        input logic [31:0] Address,
        input logic ReadEnable,
        input logic [3:0] WriteMask,
        input logic [31:0] WriteData
    );
        if ($isunknown(Address) || $isunknown(ReadEnable)
            || Address<32'ha0000000 || Address>=32'ha0080000)
            $fatal(1,"INVALID_SHARED_ADDRESS_OR_CONTROL addr=%h read=%b mask=%b data=%h",Address,ReadEnable,WriteMask,WriteData);
        // ICB write mask/data have no meaning for reads. A write must have
        // known data and mask; payload-specific checks below remain strict.
        if (ReadEnable===1'b0 && ($isunknown(WriteMask) || $isunknown(WriteData)))
            $fatal(1,"UNKNOWN_EFFECTIVE_SHARED_WRITE addr=%h read=%b mask=%b data=%h",Address,ReadEnable,WriteMask,WriteData);
    endtask
initial begin
if (!$value$plusargs("CASE=%d",CaseId)) $fatal(1,"No case");
case(CaseId)
0: CheckSharedRequest(32'ha0000000,1'b1,4'bxxxx,32'hxxxxxxxx);
1: CheckSharedRequest(32'ha0000000,1'b0,4'bxxxx,32'h12345678);
2: CheckSharedRequest(32'ha0000000,1'b0,4'hf,32'hxxxxxxxx);
3: CheckSharedRequest(32'hxxxxxxxx,1'b1,4'hf,32'h0);
4: CheckSharedRequest(32'ha0000000,1'bx,4'hf,32'h0);
5: CheckSharedRequest(32'h0,1'b1,4'hf,32'h0);
6: CheckSharedRequest(32'ha0000000,1'b0,4'hf,32'h12345678);
endcase
$display("GUARD_UNIT_ACCEPT case=%0d",CaseId);$finish;
end
endmodule
