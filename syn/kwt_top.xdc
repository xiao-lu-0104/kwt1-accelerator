# Clock constraint for the KWT-1 top level (Artix-7 estimate flow).
# 150 MHz -> 6.667 ns.

create_clock -name clk -period 6.667 [get_ports clk]

# The parameter ROM feeds wgt nibbles; keep it in the same clock domain.
set_input_delay  -clock clk 2.0 [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -clock clk 2.0 [all_outputs]

set_load 0.05 [all_outputs]
