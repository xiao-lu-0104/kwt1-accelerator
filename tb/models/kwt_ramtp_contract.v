`timescale 1ns / 1ps
// LOCAL TEST DOUBLE ONLY. Not a foundry timing/functional model. Conservative
// active-port edge-separation checks catch a coincident-clock implementation;
// no Liberty interpolation, real macro row mapping, or silicon qualification.
`ifdef KWT_LOCAL_SRAM_CONTRACT
module kwt_ramtp_contract #(parameter DEPTH=128, parameter AW=$clog2(DEPTH))
    (output reg [15:0] QA, input CLKA,CENA, input [AW-1:0] AA,
     input CLKB,CENB, input [15:0] WENB, input [AW-1:0] AB,
     input [15:0] DB, input [2:0] EMAA,EMAB, input RET1N,COLLDISN);
    reg [15:0] mem[0:DEPTH-1];
    realtime last_read=-100, last_write=-100;
    integer bit_index;
    always @(posedge CLKA) if(CENA === 1'b0) begin
        last_read=$realtime;
        // #0 observes both active clocks in a coincident-edge negative test.
        #0;
        if(($realtime-last_write)<3.0)
            $fatal(1,"LOCAL_CONTRACT_COLLISION: B-to-A edge separation below 3 ns");
        QA <= mem[AA];
    end
    always @(posedge CLKB) if(CENB === 1'b0 && WENB !== 16'hffff) begin
        last_write=$realtime;
        #0;
        if(($realtime-last_read)<3.0)
            $fatal(1,"LOCAL_CONTRACT_COLLISION: A-to-B edge separation below 3 ns");
        for(bit_index=0;bit_index<16;bit_index=bit_index+1)
            if(!WENB[bit_index]) mem[AB][bit_index] <= DB[bit_index];
    end
endmodule

module RAMTP128X16(output [15:0] QA, input CLKA,CENA, input [6:0] AA,
    input CLKB,CENB, input [15:0] WENB, input [6:0] AB,
    input [15:0] DB, input [2:0] EMAA,EMAB, input RET1N,COLLDISN);
    kwt_ramtp_contract #(.DEPTH(128)) model(.*);
endmodule
module RAMTP1024X16(output [15:0] QA, input CLKA,CENA, input [9:0] AA,
    input CLKB,CENB, input [15:0] WENB, input [9:0] AB,
    input [15:0] DB, input [2:0] EMAA,EMAB, input RET1N,COLLDISN);
    kwt_ramtp_contract #(.DEPTH(1024)) model(.*);
endmodule
`endif
