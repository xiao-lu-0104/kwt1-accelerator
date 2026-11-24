// Drop-in implementation for the existing TPU_SRAM_MODEL bank interface.
// Source: server RAMSP1024X16 TT datasheet and ports audited 2026-11-02.
// This file REPLACES Sim/Sram/kwt_sp_memory_model.v in the ASIC source list.
module kwt_sp_memory_model #(
    parameter DW = 16,
    parameter DEPTH = 1024,
    parameter AW = $clog2(DEPTH)
) (
    input wire clk, input wire en, input wire write,
    input wire [AW-1:0] addr,
    input wire [DW-1:0] wdata,
    output wire [DW-1:0] rdata
);
    // synopsys translate_off
    initial begin
        if (DW != 16 || DEPTH != 1024 || AW != 10)
            $fatal(1, "Unsupported foundry bank shape");
    end
    // synopsys translate_on
    RAMSP1024X16 Macro (
`ifdef TPU_SRAM_POWER_PINS
        .VDDCE (1'b1), .VDDPE (1'b1), .VSSE (1'b0),
`endif
        .Q     (rdata),
        .CLK   (clk),
        .CEN   (~en),
        .GWEN  (~write),
        .WEN   (16'h0000),
        .A     (addr),
        .D     (wdata),
        .EMA   (3'd2),
        .EMAW  (2'd0),
        .RET1N (1'b1)
    );
endmodule
