`timescale 1ns / 1ps
// Assemble a little-endian 64-bit parameter record from two 32-bit writes.
// Connect s_* to accepted MMIO writes (the bus must honor s_ready). The
// encoder consumes one record on m_valid && m_ready. Payload remains stable
// under backpressure; reset discards both complete and half-written records.
module kwt_param_stream (
    input wire clk, input wire rst_n,
    input wire s_valid, output wire s_ready, input wire [31:0] s_data,
    output reg m_valid, input wire m_ready, output reg [63:0] m_data,
    output wire empty
);
    reg half_full;
    reg [31:0] low_word;
    assign s_ready = rst_n && (!m_valid || m_ready);
    assign empty = !half_full && !m_valid;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            half_full <= 0;
            low_word <= 0;
            m_valid <= 0;
            m_data <= 0;
        end else begin
            if (m_valid && m_ready) m_valid <= 0;
            if (s_valid && s_ready) begin
                if (!half_full) begin
                    low_word <= s_data;
                    half_full <= 1;
                end else begin
                    m_data <= {s_data,low_word};
                    m_valid <= 1;
                    half_full <= 0;
                end
            end
        end
    end
endmodule
