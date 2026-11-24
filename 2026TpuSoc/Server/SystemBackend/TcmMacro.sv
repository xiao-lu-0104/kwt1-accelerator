// Candidate physical implementation of the competition TCM RAM interface.
// CPU/LSU/TCM controllers are unchanged. Read results are valid after read edges.
module sirv_gnrl_ram #(
    parameter DP=32768, DW=64, FORCE_X2ZERO=0, MW=8, AW=15
) (
    input sd,ds,ls,rst_n,clk,cs,we,
    input [AW-1:0] addr,
    input [DW-1:0] din,
    input [MW-1:0] wem,
    output [DW-1:0] dout
);
    localparam BANKS=DP/4096;
    localparam LANES=DW/16;
    localparam SEL=AW-12;
    wire [DW-1:0] BankData[0:BANKS-1];
    reg [SEL-1:0] ReadBank;
    always @(posedge clk) if (cs && !we) ReadBank<=addr[AW-1:12];
    assign dout=BankData[ReadBank];
    for (genvar Bank=0;Bank<BANKS;Bank++) begin: Banks
        wire Enable=cs && addr[AW-1:12]==SEL'(Bank);
        for (genvar Lane=0;Lane<LANES;Lane++) begin: Lanes
            wire [15:0] WriteMask={{8{~wem[2*Lane+1]}},{8{~wem[2*Lane]}}};
            RAMSP4096X16 Macro (
                .Q(BankData[Bank][16*Lane+:16]), .CLK(clk), .CEN(~Enable),
                .GWEN(~we), .WEN(WriteMask), .A(addr[11:0]), .D(din[16*Lane+:16]),
                .EMA(3'd2), .EMAW(2'd0), .RET1N(1'b1)
            );
        end
    end
    // No RAM initialization, reset-to-zero, or simulation X replacement.
    // Sleep pins are unused by the original functional RAM and remain unused.
    // synopsys translate_off
    initial begin
        if (!((DW==64 && MW==8 && AW==15 && DP==32768) ||
              (DW==32 && MW==4 && AW==16 && DP==65536)))
            $fatal(1,"UNSUPPORTED_COMPETITION_TCM_SHAPE DW=%0d MW=%0d AW=%0d DP=%0d",DW,MW,AW,DP);
    end
    // synopsys translate_on
endmodule
