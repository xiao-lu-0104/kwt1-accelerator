`timescale 1ns/1ps
// Passive lockstep reference: consumes identical inputs; drives no DUT signal.
module IcbMirror;
    `define GB SharedTest.Cpu.u_e203_cpu.u_e203_nice_core.Bus
    logic RequestReady, ReadDataValid, ReadDataLast, ReadDataError;
    logic WriteDataReady, WriteResponseValid, WriteResponseError;
    logic IcbCommandValid, IcbCommandRead, IcbResponseReady;
    logic [127:0] ReadData;
    logic [31:0] IcbCommandAddress, IcbCommandWriteData;
    logic [1:0] IcbCommandSize;
    integer Settled = 0;
    bit Reported = 0;
    IcbRtlReference Reference (
        .Clock(`GB.Clock), .ResetN(`GB.ResetN),
        .RequestValid(`GB.RequestValid), .RequestReady(RequestReady),
        .RequestWriteEnable(`GB.RequestWriteEnable), .RequestAddress(`GB.RequestAddress),
        .RequestBeatCount(`GB.RequestBeatCount),
        .ReadDataValid(ReadDataValid), .ReadDataReady(`GB.ReadDataReady), .ReadData(ReadData),
        .ReadDataLast(ReadDataLast), .ReadDataError(ReadDataError),
        .WriteDataValid(`GB.WriteDataValid), .WriteDataReady(WriteDataReady), .WriteData(`GB.WriteData),
        .WriteDataLast(`GB.WriteDataLast), .WriteResponseValid(WriteResponseValid),
        .WriteResponseReady(`GB.WriteResponseReady), .WriteResponseError(WriteResponseError),
        .IcbCommandValid(IcbCommandValid), .IcbCommandReady(`GB.IcbCommandReady),
        .IcbCommandAddress(IcbCommandAddress), .IcbCommandRead(IcbCommandRead),
        .IcbCommandWriteData(IcbCommandWriteData), .IcbCommandSize(IcbCommandSize),
        .IcbResponseValid(`GB.IcbResponseValid), .IcbResponseReady(IcbResponseReady),
        .IcbResponseData(`GB.IcbResponseData), .IcbResponseError(`GB.IcbResponseError)
    );
    wire [5:0] ActualControl = {`GB.RequestReady, `GB.ReadDataValid, `GB.WriteDataReady,
        `GB.WriteResponseValid, `GB.IcbCommandValid, `GB.IcbResponseReady};
    wire [5:0] ExpectedControl = {RequestReady, ReadDataValid, WriteDataReady,
        WriteResponseValid, IcbCommandValid, IcbResponseReady};
    wire Mismatch = ActualControl !== ExpectedControl
        || (`GB.IcbCommandValid === 1'b1 && IcbCommandValid === 1'b1 &&
            {`GB.IcbCommandAddress, `GB.IcbCommandRead, SharedTest.Cpu.u_e203_cpu.u_e203_nice_core.nice_icb_cmd_size}
            !== {IcbCommandAddress, IcbCommandRead, IcbCommandSize})
        || (`GB.IcbCommandValid === 1'b1 && `GB.IcbCommandRead === 1'b0 &&
            `GB.IcbCommandWriteData !== IcbCommandWriteData)
        || (`GB.ReadDataValid === 1'b1 && {`GB.ReadData, `GB.ReadDataLast, `GB.ReadDataError}
            !== {ReadData, ReadDataLast, ReadDataError})
        || (`GB.WriteResponseValid === 1'b1 && `GB.WriteResponseError !== WriteResponseError);
    always @(negedge `GB.Clock) begin
        if (`GB.ResetN !== 1'b1) Settled = 0;
        else if (Settled < 3) Settled = Settled + 1;
        else if (!Reported && (Mismatch || $isunknown(ActualControl))) begin
            Reported = 1;
            $display("ICB_FIRST_DIVERGENCE: cycle=%0d actual_control=%b expected_control=%b", SharedTest.Cycles, ActualControl, ExpectedControl);
            $display("ICB_SIZE: top_actual=%b child_unused=%b expected=%b", SharedTest.Cpu.u_e203_cpu.u_e203_nice_core.nice_icb_cmd_size, `GB.IcbCommandSize, IcbCommandSize);
            $display("ICB_INPUT: request=%b write=%b addr=%h beats=%0d read_ready=%b write_valid=%b response_ready=%b",
                `GB.RequestValid, `GB.RequestWriteEnable, `GB.RequestAddress, `GB.RequestBeatCount,
                `GB.ReadDataReady, `GB.WriteDataValid, `GB.WriteResponseReady);
            $display("ICB_BUS_INPUT: cmd_ready=%b rsp_valid=%b rsp_data=%h rsp_error=%b",
                `GB.IcbCommandReady, `GB.IcbResponseValid, `GB.IcbResponseData, `GB.IcbResponseError);
            $display("ICB_ACTUAL: cmd_valid=%b addr=%h read=%b rsp_ready=%b read_valid=%b read_data=%h",
                `GB.IcbCommandValid, `GB.IcbCommandAddress, `GB.IcbCommandRead, `GB.IcbResponseReady, `GB.ReadDataValid, `GB.ReadData);
            $display("ICB_EXPECTED: cmd_valid=%b addr=%h read=%b rsp_ready=%b read_valid=%b read_data=%h state=%0d word=%0d",
                IcbCommandValid, IcbCommandAddress, IcbCommandRead, IcbResponseReady, ReadDataValid, ReadData,
                Reference.State, Reference.Word);
        end
    end
    final begin
        $display("ICB_MIRROR_FINAL: divergence_observed=%b", Reported);
        $display("ICB_FINAL_STATE: actual_state=%b actual_word=%b expected_state=%b expected_word=%b", `GB.State, `GB.Word, Reference.State, Reference.Word);
        $display("ICB_FINAL_CONTROL: actual=%b expected=%b top_size=%b child_size=%b", ActualControl, ExpectedControl, SharedTest.Cpu.u_e203_cpu.u_e203_nice_core.nice_icb_cmd_size, `GB.IcbCommandSize);
        $display("ICB_FINAL_INPUT: request=%b request_ready=%b write=%b beats=%h cmd_ready=%b rsp_valid=%b rsp_error=%b read_ready=%b", `GB.RequestValid, `GB.RequestReady, `GB.RequestWriteEnable, `GB.RequestBeatCount, `GB.IcbCommandReady, `GB.IcbResponseValid, `GB.IcbResponseError, `GB.ReadDataReady);
    end
    `undef GB
endmodule
