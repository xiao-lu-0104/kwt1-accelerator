`timescale 1ns / 1ps
// ---------------------------------------------------------------------------
// Two-port synchronous SRAM - exactly the shape of a standard dual-port macro.
//
//   port A: bidirectional (read or write)
//   port B: read only
//
// Both reads return data one cycle after the address is registered.  A write
// is read-first: if port A reads and writes the same address in one cycle, the
// read returns the old contents.  The GEMM engine never mixes load and compute
// in the same cycle, so this is harmless.
//
// DEPTH is the exact number of words (not rounded up to a power of two), which
// matters because several buffers have sizes like 396 or 1584 words.
//
// The competition rules limit the design to single/dual-port macros, so every
// wide parallel operand fetch is built from a pair of these.
//   SW / MASKW set the write-enable granularity:
//     SW = 8  -> byte enables   (activation buffer)
//     SW = WB -> element enables (weight buffer, nibble granularity)
//
// mem is left uninitialised on purpose so a missing write surfaces as X.
// ---------------------------------------------------------------------------
module kwt_sram_2p #(
    parameter DW    = 128,
    parameter AW    = 11,
    parameter DEPTH = 2048,
    parameter SW    = 8,
    parameter MASKW = DW/SW
)(
    input  wire              clk,

    // port A: read or write
    input  wire [AW-1:0]     a_addr,
    output reg  [DW-1:0]     a_q,
    input  wire              a_we,
    input  wire [DW-1:0]     a_wdata,
    input  wire [MASKW-1:0]  a_mask,

    // port B: read only
    input  wire [AW-1:0]     b_addr,
    output reg  [DW-1:0]     b_q
);

    reg [DW-1:0] mem [0:DEPTH-1];

    integer i;
    always @(posedge clk) begin
        if (a_we) begin
            for (i = 0; i < MASKW; i = i + 1)
                if (a_mask[i])
                    mem[a_addr][i*SW +: SW] <= a_wdata[i*SW +: SW];
        end
        a_q <= mem[a_addr];
        b_q <= mem[b_addr];
    end

endmodule
