`timescale 1ns / 1ps
// Same pipelined compute/quantization path, old wide K/V layout for ablation.
module tb_kwt_encoder_layer_compact_wide;
    tb_kwt_encoder_layer_compact #(.KV_SHARED(0)) test();
endmodule
