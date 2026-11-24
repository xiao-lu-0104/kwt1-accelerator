# KWT encoder synthesis constraints, maintained independently of the DC script.
# Target: 150 MHz; actual period 6.667 ns; TT baseline, ideal pre-CTS clock.
# This reproduces the recorded pre-pilot baseline, including its OPEN hold FAIL.
# The 1 ns hold budget is not an official competition requirement. Retain it
# for the split-phase candidate so the RTL change is evaluated separately
# from any later clock-budget decision. 50% duty is required by this binding;
# CLKA follows root rising, CLKB follows root falling through a real inverter.
# DC propagates the root waveform through that hardware inversion. Do not
# declare unrelated/asynchronous clocks or disable the macro clock-pair arcs.
# No false paths, multicycle paths, disabled arcs or reset exceptions are used.
# Times use the loaded timing library's ns units; load uses its capacitance unit.

create_clock -name clk -period 6.667 [get_ports clk]
set_clock_uncertainty -setup 1.0 [get_clocks clk]
set_clock_uncertainty -hold 1.0 [get_clocks clk]
set_clock_transition 0.2 [get_clocks clk]
set_input_delay -clock clk -max 0.5 [remove_from_collection [all_inputs] [get_ports clk]]
set_input_delay -clock clk -min 0.5 [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -clock clk -max 0.5 [all_outputs]
set_output_delay -clock clk -min 0.5 [all_outputs]
set_load 0.02 [all_outputs]
