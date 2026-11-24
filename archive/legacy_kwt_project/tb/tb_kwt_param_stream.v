`timescale 1ns / 1ps
module tb_kwt_param_stream;
    reg clk=0, rst_n=0, s_valid=0, m_ready=0;
    reg [31:0] s_data=0;
    wire s_ready,m_valid,empty;
    wire [63:0] m_data;
    reg random_run=0;
    integer sent=0,received=0,seed=120491;
    reg stalled=0;
    reg source_accepted=0;
    reg [63:0] held;
    kwt_param_stream dut(.*);
    always #5 clk=~clk;
    function [31:0] word_value(input integer index);
        word_value=32'h59130000 ^ (index*32'h10001);
    endfunction
    task send_word(input [31:0] value);
        begin
            @(negedge clk); s_data=value; s_valid=1;
            @(posedge clk); while(!s_ready) @(posedge clk);
            @(negedge clk); s_valid=0;
        end
    endtask
    always @(negedge clk) if(random_run) begin
        m_ready=($random(seed)&3)!=0;
        if(!s_valid || source_accepted) begin
            s_valid=(sent<512)&&(($random(seed)&3)!=0);
            s_data=word_value(sent);
        end
    end
    always @(posedge clk) if(random_run) begin
        source_accepted=s_valid&&s_ready;
        if(stalled && (!m_valid || m_data!==held)) $fatal(1,"Stream changed a stalled record");
        stalled=m_valid&&!m_ready; held=m_data;
        if(source_accepted) sent<=sent+1;
        if(m_valid&&m_ready) begin
            if(m_data!=={word_value(2*received+1),word_value(2*received)})
                $fatal(1,"Stream pair/order mismatch at record %0d got=%h",received,m_data);
            received=received+1;
        end
    end
    initial begin
        repeat(2) @(negedge clk); rst_n=1;
        send_word(32'hdeadbeef);
        if(empty) $fatal(1,"Half record incorrectly marked empty");
        rst_n=0; @(negedge clk); rst_n=1;
        send_word(32'h11112222); send_word(32'h33334444);
        repeat(5) @(negedge clk);
        if(!m_valid || m_data!==64'h3333444411112222 || s_ready)
            $fatal(1,"Reset/record backpressure failed");
        rst_n=0; @(negedge clk); rst_n=1; random_run=1;
        wait(received==256);
        @(negedge clk); random_run=0; s_valid=0;
        if(sent!=512 || !empty) $fatal(1,"Stream did not drain");
        $display("PASS: parameter stream 256 records / random backpressure / partial-record reset");
        $finish;
    end
    initial begin #100000; $fatal(1,"Parameter stream timeout"); end
endmodule
