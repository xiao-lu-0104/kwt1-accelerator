`ifndef KWT_SRAM_PINS_VH
`define KWT_SRAM_PINS_VH
// Competition SRAM_Lib_2025 RAMTP128X16 / RAMTP1024X16.
// Checked against server model/control excerpts on 2026-10-29.
// Both ports use the same rising-edge clock. CEN and bit write masks are low
// active. RET1N=1 selects normal operation; the model specifies EMA=2.
// Keep collision detection ENABLED (COLLDISN=1). Forwarding must tolerate X on
// a read/write collision; disabling the checker would conceal a real hazard.
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
