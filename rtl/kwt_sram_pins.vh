`ifndef KWT_SRAM_PINS_VH
`define KWT_SRAM_PINS_VH
// Competition SRAM_Lib_2025 RAMTP128X16 / RAMTP1024X16.
// Checked against server model/control excerpts on 2026-10-29.
// CEN and bit write masks are low active. RET1N=1 selects normal operation;
// the model specifies EMA=2. A reads on clk rising; B writes on clk falling,
// using a transaction captured on clk rising. Both macro pins are rising-edge
// triggered. Preserve the physical clock inversion in implementation/STA.
// Keep collision detection ENABLED (COLLDISN=1). The datasheet does not
// guarantee a write during a same-row collision with detection enabled;
// forwarding alone cannot make a coincident-clock binding safe.
`define KWT_SRAM_READ_ENABLE    1'b0
`define KWT_SRAM_READ_DISABLE   1'b1
`define KWT_SRAM_WRITE_ENABLE   1'b0
`define KWT_SRAM_WRITE_DISABLE  1'b1
`define KWT_SRAM_WRITE_MASK     16'h0000
`define KWT_SRAM_NO_WRITE_MASK  16'hffff
`define KWT_SRAM_EMAA           3'd2
`define KWT_SRAM_EMAB           3'd2
`define KWT_SRAM_RET1N          1'b1
`define KWT_SRAM_COLLDISN       1'b1
`endif
