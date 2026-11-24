`timescale 1ns/1ps
module SpBindingTest;
    logic Clock;
    // Full-cycle, common rising edge clock, 150 MHz nominal.
    initial begin Clock = 0; forever #3.333333 Clock = ~Clock; end
    logic SramReadAValid = 0, SramReadBValid = 0, SramWriteValid = 0;
    logic [13:0] SramReadAAddress = 0, SramReadBAddress = 0, SramWriteAddress = 0;
    logic [127:0] SramReadAData, SramReadBData, SramWriteData = 0;
    logic [7:0] SramWriteMask = 0;
    logic [127:0] Expected [7][3];
    int Checked = 0;
    TpuSram Dut (.*);

    function automatic logic [13:0] Address(input int Region, input int Location);
        int Offset;
        case (Location)
            0: Offset = 0;
            1: Offset = 1;
            default: Offset = 1023;
        endcase
        return 14'(Region * 1024 + Offset);
    endfunction
    function automatic logic [127:0] Pattern(input int Region, input int Location, input int Salt);
        logic [127:0] Value;
        for (int Lane = 0; Lane < 8; Lane++)
            Value[16*Lane +: 16] = 16'((Region+1)*4099 ^ Location*257 ^ Lane*31 ^ Salt);
        return Value;
    endfunction
    task automatic WriteWord(input int Region, input int Location,
                             input logic [127:0] Value, input logic [7:0] Mask);
        @(negedge Clock);
        SramWriteValid = 1;
        SramWriteAddress = Address(Region, Location);
        SramWriteData = Value;
        SramWriteMask = Mask;
        @(negedge Clock);
        SramWriteValid = 0;
        SramWriteMask = 0;
        // The request stages commit into the macro at the next rising edge.
        repeat (2) @(negedge Clock);
        for (int Lane = 0; Lane < 8; Lane++)
            if (Mask[Lane]) Expected[Region][Location][16*Lane +: 16] = Value[16*Lane +: 16];
    endtask
    task automatic ReadPair(input int RegionA, input int RegionB, input int Location);
        @(negedge Clock);
        SramReadAValid = 1;
        SramReadBValid = 1;
        SramReadAAddress = Address(RegionA, Location);
        SramReadBAddress = Address(RegionB, Location);
        @(posedge Clock); // request accepted
        @(negedge Clock);
        SramReadAValid = 0;
        SramReadBValid = 0;
        @(posedge Clock); // macro read, output follows after library/model Tco
        @(posedge Clock); // TPU output register samples the previous macro read
        #0.05;
        if (SramReadAData !== Expected[RegionA][Location])
            $fatal(1, "SP A mismatch region=%0d location=%0d got=%h expected=%h",
                   RegionA, Location, SramReadAData, Expected[RegionA][Location]);
        if (SramReadBData !== Expected[RegionB][Location])
            $fatal(1, "SP B mismatch region=%0d location=%0d got=%h expected=%h",
                   RegionB, Location, SramReadBData, Expected[RegionB][Location]);
        Checked += 2;
    endtask
    initial begin
        repeat (5) @(negedge Clock);
        for (int Region = 0; Region < 7; Region++)
            for (int Location = 0; Location < 3; Location++)
                WriteWord(Region, Location, Pattern(Region, Location, 'h1234), 8'hff);
        for (int Region = 0; Region < 7; Region++)
            for (int Location = 0; Location < 3; Location++)
                ReadPair(Region, (Region+1)%7, Location);
        for (int Mask = 0; Mask < 256; Mask++) begin
            WriteWord(Mask%7, Mask%3, Pattern(Mask%7, Mask%3, Mask*1031), 8'(Mask));
            ReadPair(Mask%7, (Mask+1)%7, Mask%3);
        end
        // Idle and live bus changes must not write memory.
        repeat (8) begin
            @(negedge Clock);
            SramWriteAddress = 14'h1bff;
            SramWriteData = ~SramWriteData;
            SramWriteMask = 8'hff;
        end
        for (int Region = 0; Region < 7; Region++)
            ReadPair(Region, (Region+2)%7, 2);
        $display("PASS SP_BINDING: 56 banks, 150MHz full-cycle, boundaries, 256 masks, read latency, idle; %0d checked words", Checked);
        $finish;
    end
    initial begin #100000; $fatal(1, "SP binding watchdog"); end
endmodule
