`timescale 1ns / 1ps
// Same public-port and golden-vector checks with the legacy compute backend.
module tb_kwt_encoder_12_legacy;
    tb_kwt_encoder_12 #(.COMPACT(0)) test();
endmodule
