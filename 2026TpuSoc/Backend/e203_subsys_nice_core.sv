// Replacement for the platform's demonstration NICE engine. Compile this
// module instead of its original file; the upstream CPU/LSU remain unchanged.
module e203_subsys_nice_core (
    input  logic nice_clk,
    input  logic nice_rst_n,
    output logic nice_active,
    output logic nice_mem_holdup,
    input  logic nice_req_valid,
    output logic nice_req_ready,
    input  logic [31:0] nice_req_inst,
    input  logic [31:0] nice_req_rs1,
    input  logic [31:0] nice_req_rs2,
    output logic nice_rsp_valid,
    input  logic nice_rsp_ready,
    output logic [31:0] nice_rsp_rdat,
    output logic nice_rsp_err,
    output logic nice_icb_cmd_valid,
    input  logic nice_icb_cmd_ready,
    output logic [31:0] nice_icb_cmd_addr,
    output logic nice_icb_cmd_read,
    output logic [31:0] nice_icb_cmd_wdata,
    output logic [1:0] nice_icb_cmd_size,
    input  logic nice_icb_rsp_valid,
    output logic nice_icb_rsp_ready,
    input  logic [31:0] nice_icb_rsp_rdata,
    input  logic nice_icb_rsp_err
);
    logic RequestValid, RequestReady, RequestWrite;
    logic [31:0] RequestAddress;
    logic [15:0] RequestBeats;
    logic ReadValid, ReadReady, ReadLast, ReadError;
    logic WriteValid, WriteReady, WriteLast, ResponseValid, ResponseReady, ResponseError;
    logic [127:0] ReadData, WriteData;
    assign nice_mem_holdup = 1'b0;
    TpuNice Tpu (
        .Clock(nice_clk), .ResetN(nice_rst_n),
        .NiceRequestValid(nice_req_valid), .NiceRequestReady(nice_req_ready),
        .NiceRequestInstruction(nice_req_inst), .NiceRequestSource1Data(nice_req_rs1),
        .NiceRequestSource2Data(nice_req_rs2), .NiceResponseValid(nice_rsp_valid),
        .NiceResponseReady(nice_rsp_ready), .NiceResponseData(nice_rsp_rdat),
        .NiceResponseError(nice_rsp_err), .NiceActive(nice_active),
        .MemoryRequestValid(RequestValid), .MemoryRequestReady(RequestReady),
        .MemoryRequestWriteEnable(RequestWrite), .MemoryRequestAddress(RequestAddress),
        .MemoryRequestBeatCount(RequestBeats), .MemoryReadDataValid(ReadValid),
        .MemoryReadDataReady(ReadReady), .MemoryReadData(ReadData),
        .MemoryReadDataLast(ReadLast), .MemoryReadDataError(ReadError),
        .MemoryWriteDataValid(WriteValid), .MemoryWriteDataReady(WriteReady),
        .MemoryWriteData(WriteData), .MemoryWriteDataLast(WriteLast),
        .MemoryWriteResponseValid(ResponseValid), .MemoryWriteResponseReady(ResponseReady),
        .MemoryWriteResponseError(ResponseError)
    );
    TpuIcb Bus (
        .Clock(nice_clk), .ResetN(nice_rst_n),
        .RequestValid(RequestValid), .RequestReady(RequestReady),
        .RequestWriteEnable(RequestWrite), .RequestAddress(RequestAddress), .RequestBeatCount(RequestBeats),
        .ReadDataValid(ReadValid), .ReadDataReady(ReadReady), .ReadData(ReadData),
        .ReadDataLast(ReadLast), .ReadDataError(ReadError),
        .WriteDataValid(WriteValid), .WriteDataReady(WriteReady), .WriteData(WriteData), .WriteDataLast(WriteLast),
        .WriteResponseValid(ResponseValid), .WriteResponseReady(ResponseReady), .WriteResponseError(ResponseError),
        .IcbCommandValid(nice_icb_cmd_valid), .IcbCommandReady(nice_icb_cmd_ready),
        .IcbCommandAddress(nice_icb_cmd_addr), .IcbCommandRead(nice_icb_cmd_read),
        .IcbCommandWriteData(nice_icb_cmd_wdata), .IcbCommandSize(nice_icb_cmd_size),
        .IcbResponseValid(nice_icb_rsp_valid), .IcbResponseReady(nice_icb_rsp_ready),
        .IcbResponseData(nice_icb_rsp_rdata), .IcbResponseError(nice_icb_rsp_err)
    );
endmodule
