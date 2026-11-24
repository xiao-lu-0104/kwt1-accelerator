`timescale 1ns / 1ps
// Macro boundary: one synchronous read port and one full-word write port.
// KWT_ASIC_SRAM selects kwt_foundry_sram16 and a verified kwt_sram_pins.vh.
// 4096 words use four 1024-word RAMTP banks (no 4096-word RAMTP was supplied).
// No inferred bit masks. See doc/SRAM宏绑定操作.md for current validation status.
module kwt_mem16 #(parameter DEPTH=128, parameter AW=$clog2(DEPTH)) (
    input wire clk, input wire we, input wire [AW-1:0] wa,
    input wire [15:0] wd, input wire [AW-1:0] ra,
    output wire [15:0] rd
);
`ifdef KWT_ASIC_SRAM
    kwt_foundry_sram16 #(.DEPTH(DEPTH), .AW(AW)) u_macro
        (.clk(clk), .we(we), .wa(wa), .wd(wd), .ra(ra), .rd(rd));
`else
    reg [15:0] mem [0:DEPTH-1];
    reg [15:0] q;
    always @(posedge clk) begin
        if (we) mem[wa] <= wd;
        q <= mem[ra];
    end
    assign rd=q;
`endif
endmodule

// Accepts a masked update every cycle, even if the macro has no write masks.
// Read/modify/write has one pending update; forwarding handles consecutive
// updates to the same word. Independent banks do not replicate stored data.
// Read latency is one cycle. wr and compute reads are mutually exclusive.
module kwt_packed_sram #(
    parameter DW=128, parameter DEPTH=1024, parameter AW=$clog2(DEPTH)
)(
    input wire clk, input wire rst_n,
    input wire wr, input wire [AW-1:0] wa,
    input wire [DW-1:0] wd, input wire [DW/4-1:0] mask,
    input wire [AW-1:0] ra, output wire [DW-1:0] rd
);
    genvar b, n;
    generate for (b=0; b<DW/16; b=b+1) begin: g_bank
        wire update = wr && (|mask[b*4 +: 4]);
        reg pending;
        reg [AW-1:0] pending_addr;
        reg [15:0] pending_data;
        reg [3:0] pending_mask;
        reg committed;
        reg [AW-1:0] committed_addr;
        reg [15:0] committed_data;
        wire [15:0] old_data;
        wire [15:0] base = (committed && committed_addr==pending_addr)
                                  ? committed_data : old_data;
        wire [15:0] merged;
        for (n=0; n<4; n=n+1) begin: g_merge
            assign merged[n*4 +: 4] = pending_mask[n]
                           ? pending_data[n*4 +: 4] : base[n*4 +: 4];
        end
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                pending<=0; committed<=0;
                pending_addr<=0; pending_data<=0; pending_mask<=0;
                committed_addr<=0; committed_data<=0;
            end else begin
                pending<=update;
                pending_addr<=wa;
                pending_data<=wd[b*16 +: 16];
                pending_mask<=mask[b*4 +: 4];
                committed<=pending;
                committed_addr<=pending_addr;
                committed_data<=merged;
            end
        end
        kwt_mem16 #(.DEPTH(DEPTH), .AW(AW)) u_mem (
            .clk(clk), .we(pending), .wa(pending_addr), .wd(merged),
            .ra(update ? wa : ra), .rd(old_data));
        assign rd[b*16 +: 16]=old_data;
    end endgenerate
endmodule
