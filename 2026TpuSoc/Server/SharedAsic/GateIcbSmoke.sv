`timescale 1ns/1ps
module GateIcbSmoke;
    logic Clock = 0, ResetN = 0, RequestValid = 0;
    wire RequestReady, ReadValid, ReadLast, ReadError, CommandValid, CommandRead, ResponseReady;
    wire [127:0] Data;
    wire [31:0] Address, WriteData;
    wire [1:0] UnusedSize;
    logic ResponseValid = 0;
    logic [31:0] ResponseData = 0;
    integer Cycles = 0, Words = 0, Beats = 0;
    TpuIcb Dut (
        .Clock(Clock), .ResetN(ResetN), .RequestValid(RequestValid), .RequestReady(RequestReady),
        .RequestWriteEnable(1'b0), .RequestAddress(32'h90001000), .RequestBeatCount(16'd792),
        .ReadDataValid(ReadValid), .ReadDataReady(1'b1), .ReadData(Data), .ReadDataLast(ReadLast), .ReadDataError(ReadError),
        .WriteDataValid(1'b0), .WriteDataReady(), .WriteData(128'b0), .WriteDataLast(1'b0),
        .WriteResponseValid(), .WriteResponseReady(1'b0), .WriteResponseError(),
        .IcbCommandValid(CommandValid), .IcbCommandReady(1'b1), .IcbCommandAddress(Address),
        .IcbCommandRead(CommandRead), .IcbCommandWriteData(WriteData), .IcbCommandSize(UnusedSize),
        .IcbResponseValid(ResponseValid), .IcbResponseReady(ResponseReady),
        .IcbResponseData(ResponseData), .IcbResponseError(1'b0)
    );
    initial forever #5 Clock = !Clock;
    initial begin
        repeat (8) @(negedge Clock);
        ResetN = 1;
        @(negedge Clock);
        RequestValid = 1;
        do begin
            @(posedge Clock);
            if ($isunknown(RequestReady)) $fatal(1, "ICB_UNIT_UNKNOWN_REQUEST_READY");
        end while (!RequestReady);
        @(negedge Clock);
        RequestValid = 0;
    end
    always @(posedge Clock) begin
        if (!ResetN) begin ResponseValid <= 0; Cycles = 0; end
        else begin
            Cycles = Cycles + 1;
            if (Cycles > 200) $fatal(1, "ICB_UNIT_WATCHDOG words=%0d beats=%0d", Words, Beats);
            if (Cycles > 2 && $isunknown({RequestReady, ReadValid, CommandValid, ResponseReady}))
                $fatal(1, "ICB_UNIT_UNKNOWN_CONTROL cycle=%0d req=%b read=%b cmd=%b rsp=%b", Cycles, RequestReady, ReadValid, CommandValid, ResponseReady);
            if (ResponseValid && ResponseReady) ResponseValid <= 0;
            if (CommandValid) begin
                if (CommandRead !== 1'b1 || Address !== (32'h90001000 + 32'(Words * 4)))
                    $fatal(1, "ICB_UNIT_COMMAND word=%0d addr=%h read=%b", Words, Address, CommandRead);
                if (ResponseValid) $fatal(1, "ICB_UNIT_OVERLAPPING_COMMAND");
                ResponseData <= 32'h12340000 + 32'(Words);
                ResponseValid <= 1;
                Words = Words + 1;
            end
            if (ReadValid) begin
                for (int Index = 0; Index < 4; Index++)
                    if (Data[Index * 32 +: 32] !== (32'h12340000 + 32'(Beats * 4 + Index)))
                        $fatal(1, "ICB_UNIT_DATA beat=%0d word=%0d actual=%h", Beats, Index, Data[Index * 32 +: 32]);
                if (ReadLast !== 1'b0 || ReadError !== 1'b0) $fatal(1, "ICB_UNIT_FLAGS");
                Beats = Beats + 1;
                if (Beats == 2) begin
                    $display("PASS ICB_UNIT: first 8 words / 2 beats of 792-beat request; mapped module only");
                    $finish;
                end
            end
        end
    end
    final $display("ICB_UNIT_FINAL: cycles=%0d words=%0d beats=%0d", Cycles, Words, Beats);
endmodule
