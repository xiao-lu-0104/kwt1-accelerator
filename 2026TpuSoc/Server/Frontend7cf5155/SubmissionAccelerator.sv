// Integration-only scoring boundary. Upstream TpuNice/TpuIcb bodies are unchanged.
// NICE control plus one ICB32 master; no private path to platform SRAM.
module SubmissionAccelerator (
    input logic Clock, ResetN,
    input logic NiceRequestValid,
    output logic NiceRequestReady,
    input logic [31:0] NiceInst,NiceRs1,NiceRs2,
    output logic NiceResponseValid,
    input logic NiceResponseReady,
    output logic [31:0] NiceResponseData,
    output logic NiceResponseError,NiceMemoryHold,
    output logic ComputeActive,DmaActive,LoaderActive,
    output logic SystemRequestValid,
    input logic SystemRequestReady,
    output logic [31:0] SystemRequestAddress,
    output logic SystemRequestReadEnable,
    output logic [31:0] SystemRequestWriteData,
    output logic [3:0] SystemRequestWriteMask,
    input logic SystemResponseValid,
    output logic SystemResponseReady,
    input logic [31:0] SystemResponseData,
    input logic SystemResponseError
);
    localparam bit FastIcb=1;
    logic MemoryBusy,InternalNiceMemoryHold;
    assign NiceMemoryHold=InternalNiceMemoryHold || MemoryBusy;
    logic         CopyRequestValid;
    logic         CopyRequestReady;
    logic [31:0]  CopySourceAddress;
    logic [31:0]  CopyDestinationAddress;
    logic [15:0]  CopyWordCount;
    logic         CopyResponseValid;
    logic         CopyResponseReady;
    logic         CopyResponseError;
    logic         MemoryRequestValid;
    logic         MemoryRequestReady;
    logic         MemoryRequestWriteEnable;
    logic [31:0]  MemoryRequestAddress;
    logic [15:0]  MemoryRequestBeatCount;
    logic         MemoryReadDataValid;
    logic         MemoryReadDataReady;
    logic [127:0] MemoryReadData;
    logic         MemoryReadDataLast;
    logic         MemoryReadDataError;
    logic         MemoryWriteDataValid;
    logic         MemoryWriteDataReady;
    logic [127:0] MemoryWriteData;
    logic         MemoryWriteDataLast;
    logic         MemoryWriteResponseValid;
    logic         MemoryWriteResponseError;
    logic         MemoryWriteResponseReady;
    TpuNice #(
        .BlockDmaResponse            (1)
    ) Tpu (
        .Clock                       (Clock),
        .ResetN                      (ResetN),
        .NiceRequestValid            (NiceRequestValid),
        .NiceRequestReady            (NiceRequestReady),
        .NiceRequestInstruction      (NiceInst),
        .NiceRequestSource1Data      (NiceRs1),
        .NiceRequestSource2Data      (NiceRs2),
        .NiceResponseValid           (NiceResponseValid),
        .NiceResponseReady           (NiceResponseReady),
        .NiceResponseData            (NiceResponseData),
        .NiceResponseError           (NiceResponseError),
        .NiceActive                  (),
        .NiceMemoryHold              (InternalNiceMemoryHold),
        .ComputeBusy                 (ComputeActive),
        .DmaBusy                     (DmaActive),
        .CopyRequestValid            (CopyRequestValid),
        .CopyRequestReady            (CopyRequestReady),
        .CopySourceAddress           (CopySourceAddress),
        .CopyDestinationAddress      (CopyDestinationAddress),
        .CopyWordCount               (CopyWordCount),
        .CopyResponseValid           (CopyResponseValid),
        .CopyResponseReady           (CopyResponseReady),
        .CopyResponseError           (CopyResponseError),
        .CopyBusy                    (LoaderActive),
        .MemoryRequestValid          (MemoryRequestValid),
        .MemoryRequestReady          (MemoryRequestReady),
        .MemoryRequestWriteEnable    (MemoryRequestWriteEnable),
        .MemoryRequestAddress        (MemoryRequestAddress),
        .MemoryRequestBeatCount      (MemoryRequestBeatCount),
        .MemoryReadDataValid         (MemoryReadDataValid),
        .MemoryReadDataReady         (MemoryReadDataReady),
        .MemoryReadData              (MemoryReadData),
        .MemoryReadDataLast          (MemoryReadDataLast),
        .MemoryReadDataError         (MemoryReadDataError),
        .MemoryWriteDataValid        (MemoryWriteDataValid),
        .MemoryWriteDataReady        (MemoryWriteDataReady),
        .MemoryWriteData             (MemoryWriteData),
        .MemoryWriteDataLast         (MemoryWriteDataLast),
        .MemoryWriteResponseValid    (MemoryWriteResponseValid),
        .MemoryWriteResponseError    (MemoryWriteResponseError),
        .MemoryWriteResponseReady    (MemoryWriteResponseReady)
    );
    TpuIcb #(
        .FastIcb (FastIcb)
    ) Bus (
        .Clock                       (Clock),
        .ResetN                      (ResetN),
        .Busy                        (MemoryBusy),
        .CopyRequestValid            (CopyRequestValid),
        .CopyRequestReady            (CopyRequestReady),
        .CopySourceAddress           (CopySourceAddress),
        .CopyDestinationAddress      (CopyDestinationAddress),
        .CopyWordCount               (CopyWordCount),
        .CopyResponseValid           (CopyResponseValid),
        .CopyResponseReady           (CopyResponseReady),
        .CopyResponseError           (CopyResponseError),
        .CopyBusy                    (LoaderActive),
        .RequestValid                (MemoryRequestValid),
        .RequestReady                (MemoryRequestReady),
        .RequestWriteEnable          (MemoryRequestWriteEnable),
        .RequestAddress              (MemoryRequestAddress),
        .RequestBeatCount            (MemoryRequestBeatCount),
        .ReadDataValid               (MemoryReadDataValid),
        .ReadDataReady               (MemoryReadDataReady),
        .ReadData                    (MemoryReadData),
        .ReadDataLast                (MemoryReadDataLast),
        .ReadDataError               (MemoryReadDataError),
        .WriteDataValid              (MemoryWriteDataValid),
        .WriteDataReady              (MemoryWriteDataReady),
        .WriteData                   (MemoryWriteData),
        .WriteDataLast               (MemoryWriteDataLast),
        .WriteResponseValid          (MemoryWriteResponseValid),
        .WriteResponseError          (MemoryWriteResponseError),
        .WriteResponseReady          (MemoryWriteResponseReady),
        .SystemRequestValid          (SystemRequestValid),
        .SystemRequestReady          (SystemRequestReady),
        .SystemRequestAddress        (SystemRequestAddress),
        .SystemRequestReadEnable     (SystemRequestReadEnable),
        .SystemRequestWriteData      (SystemRequestWriteData),
        .SystemRequestWriteMask      (SystemRequestWriteMask),
        .SystemResponseValid         (SystemResponseValid),
        .SystemResponseReady         (SystemResponseReady),
        .SystemResponseData          (SystemResponseData),
        .SystemResponseError         (SystemResponseError)
    );
endmodule
