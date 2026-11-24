`timescale 1ns / 1ps
// GELU lookup: int8 in (scale s_hin) -> int8 out (scale s_h).
// Index = clamp(x + 127, 0, 254). Bit-exact with fixed_encoder's GELU stage.
module kwt_gelu (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               valid_in,
    input  wire signed [7:0]  x_in,
    output reg  signed [7:0]  y_out,
    output reg                valid_out
);

    wire signed [8:0] idx_s = $signed(x_in) + 9'sd127;
    wire [7:0] idx = (idx_s < 0) ? 8'd0 :
                     (idx_s > 9'sd254) ? 8'd254 : idx_s[7:0];

    wire signed [7:0] lut_val;
    kwt_gelu_lut u_lut (.idx(idx), .val(lut_val));

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            y_out     <= 8'sd0;
            valid_out <= 1'b0;
        end else begin
            valid_out <= valid_in;
            if (valid_in)
                y_out <= lut_val;
        end
    end

endmodule
