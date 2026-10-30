`timescale 1ns / 1ps
// RAMTP binding. Pin constants follow the competition model excerpts; see
// kwt_sram_pins.vh. Real foundry-model regression is separate from local tests.
// Default vendor-model compilation uses logical ports only. Explicit power
// pins below are optional and require a matching vendor preprocessor branch.
`ifdef KWT_ASIC_SRAM
`include "kwt_sram_pins.vh"
module kwt_foundry_sram16 #(
    parameter DEPTH=128, parameter AW=$clog2(DEPTH)
)(
    input wire clk, input wire we, input wire [AW-1:0] wa,
    input wire [15:0] wd, input wire [AW-1:0] ra,
    output wire [15:0] rd
);
    // Logical transactions are accepted at the rising edge. A reads at that
    // edge; B commits the captured write at the following falling edge. This
    // preserves read-before-write and next-cycle visibility while separating
    // the macro clocks by half a cycle (3.3335 ns at 150 MHz, 50% duty).
    // Capturing ALL write signals is essential: packed-SRAM RMW data changes
    // after the rising edge. Driving B directly would write the next request.
    reg write_enable;
    reg [AW-1:0] write_address;
    reg [15:0] write_data;
    wire write_clock = ~clk;
    always @(posedge clk) begin
        write_enable <= we;
        write_address <= wa;
        write_data <= wd;
    end
`ifdef KWT_SRAM_POWER_PINS
    supply1 vdd;
    supply0 vss;
`endif
    generate
        if (AW != $clog2(DEPTH)) begin: g_bad_width
            KWT_SRAM_INVALID_ADDRESS_WIDTH invalid_configuration();
        end else if (DEPTH == 128) begin: g_128
            RAMTP128X16 u_ram (
`ifdef KWT_SRAM_POWER_PINS
                .VDDCE(vdd), .VDDPE(vdd), .VSSE(vss),
`endif
                .QA(rd), .CLKA(clk), .CENA(`KWT_SRAM_READ_ENABLE), .AA(ra),
                .CLKB(write_clock), .CENB(write_enable ? `KWT_SRAM_WRITE_ENABLE : `KWT_SRAM_WRITE_DISABLE),
                .WENB(write_enable ? `KWT_SRAM_WRITE_MASK : `KWT_SRAM_NO_WRITE_MASK),
                .AB(write_address), .DB(write_data), .EMAA(`KWT_SRAM_EMAA), .EMAB(`KWT_SRAM_EMAB),
                .RET1N(`KWT_SRAM_RET1N), .COLLDISN(`KWT_SRAM_COLLDISN));
        end else if (DEPTH == 1024 || DEPTH == 4096) begin: g_banked
            localparam BANKS=DEPTH/1024;
            // A logical 4096-word SRAM uses four 1024-word 1R1W macros.
            // Register the READ bank, not the current combinational address:
            // this mux adds no cycle to the synchronous macro read latency.
            wire [15:0] bank_q [0:BANKS-1];
            if (BANKS == 1) begin: g_single
                assign rd=bank_q[0];
            end else begin: g_mux
                reg [1:0] read_bank;
                always @(posedge clk) read_bank <= ra[11:10];
                assign rd=bank_q[read_bank];
            end
            genvar bank;
            for (bank=0; bank<BANKS; bank=bank+1) begin: g_bank
                // Division is a power-of-two slice after elaboration. The
                // expression is also legal for AW=10 (no invalid part-select).
                wire bank_we=write_enable && ((write_address >> 10) == bank);
                wire bank_read=((ra >> 10) == bank);
                RAMTP1024X16 u_ram (
`ifdef KWT_SRAM_POWER_PINS
                    .VDDCE(vdd), .VDDPE(vdd), .VSSE(vss),
`endif
                    .QA(bank_q[bank]), .CLKA(clk),
                    .CENA(bank_read ? `KWT_SRAM_READ_ENABLE : `KWT_SRAM_READ_DISABLE),
                    .AA(ra[9:0]), .CLKB(write_clock),
                    .CENB(bank_we ? `KWT_SRAM_WRITE_ENABLE : `KWT_SRAM_WRITE_DISABLE),
                    .WENB(bank_we ? `KWT_SRAM_WRITE_MASK : `KWT_SRAM_NO_WRITE_MASK),
                    .AB(write_address[9:0]), .DB(write_data),
                    .EMAA(`KWT_SRAM_EMAA), .EMAB(`KWT_SRAM_EMAB),
                    .RET1N(`KWT_SRAM_RET1N), .COLLDISN(`KWT_SRAM_COLLDISN));
            end
        end else begin: g_bad_depth
            KWT_SRAM_UNSUPPORTED_DEPTH invalid_configuration();
        end
    endgenerate
endmodule
`endif
