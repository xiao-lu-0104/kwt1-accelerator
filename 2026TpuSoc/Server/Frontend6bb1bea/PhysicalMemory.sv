// Physical single-port SRAM endpoints. One outstanding response, no bypass port.
module PhysicalMemory #(parameter int Bytes=65536, DW=32)(
    input logic Clock, ResetN, RequestValid,
    output logic RequestReady,
    input logic [31:0] Address,
    input logic ReadEnable,
    input logic [DW-1:0] WriteData,
    input logic [DW/8-1:0] WriteMask,
    output logic ResponseValid,
    input logic ResponseReady,
    output logic [DW-1:0] ResponseData
);
    localparam int Shift=$clog2(DW/8), Banks=Bytes/(4096*(DW/8));
    localparam int BankBits=$clog2(Banks);
    logic [BankBits-1:0] ReadBank;
    wire [BankBits-1:0] SelectedBank=Address[Shift+12+:BankBits];
    wire [DW-1:0] BankData[0:Banks-1];
    assign RequestReady=ResetN && !ResponseValid;
    assign ResponseData=BankData[ReadBank];
    always_ff @(posedge Clock) begin
        if (!ResetN) begin ResponseValid<=0; ReadBank<=0; end
        else begin
            if (ResponseValid && ResponseReady) ResponseValid<=0;
            if (RequestValid && RequestReady) begin
                ResponseValid<=1;
                ReadBank<=SelectedBank;
            end
        end
    end
    for (genvar Bank=0;Bank<Banks;Bank++) begin: BanksLoop
        for (genvar Lane=0;Lane<DW/16;Lane++) begin: Lanes
            wire Enable=RequestValid && RequestReady && SelectedBank==BankBits'(Bank);
            RAMSP4096X16 Macro (
                .Q(BankData[Bank][16*Lane+:16]),.CLK(Clock),.CEN(~Enable),
                .GWEN(ReadEnable),.WEN({{8{~WriteMask[2*Lane+1]}},{8{~WriteMask[2*Lane]}}}),
                .A(Address[Shift+:12]),.D(WriteData[16*Lane+:16]),
                .EMA(3'd2),.EMAW(2'd0),.RET1N(1'b1)
            );
        end
    end
endmodule
