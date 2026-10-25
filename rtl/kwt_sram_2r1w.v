`timescale 1ns / 1ps
// ---------------------------------------------------------------------------
// Two-read one-write synchronous SRAM.
//
// This is the operand-storage shape a standard dual-port macro provides:
//   * port A read, port B read  (registered address, data valid one cycle later)
//   * one write port with lane write-enables
//
// The competition rules limit the design to single/dual-port macros, so all
// wide parallel operand fetches are built from a pair of these plus width
// packing (several operands per word) instead of a custom many-port array.
//
// SW / MASKW define the write-enable granularity:
//   SW = 8   -> byte enables   (activation buffer)
//   SW = WB  -> element enables (weight buffer, one nibble at a time)
//
// Simulation note: mem is deliberately left uninitialised so that a missing
// write shows up as X instead of silently producing zeros.
// ---------------------------------------------------------------------------
module kwt_sram_2r1w #(
    parameter DW    = 128,
    parameter AW    = 11,
    parameter SW    = 8,
    parameter MASKW = DW/SW
)(
    input  wire              clk,

    input  wire [AW-1:0]     a_addr,
    output reg  [DW-1:0]     a_q,

    input  wire [AW-1:0]     b_addr,
    output reg  [DW-1:0]     b_q,

    input  wire              we,
    input  wire [AW-1:0]     w_addr,
    input  wire [DW-1:0]     w_data,
    input  wire [MASKW-1:0]  w_mask
);

    reg [DW-1:0] mem [0:(1<<AW)-1];

    integer i;
    always @(posedge clk) begin
        if (we) begin
            for (i = 0; i < MASKW; i = i + 1)
                if (w_mask[i])
                    mem[w_addr][i*SW +: SW] <= w_data[i*SW +: SW];
        end
        a_q <= mem[a_addr];
        b_q <= mem[b_addr];
    end

endmodule
