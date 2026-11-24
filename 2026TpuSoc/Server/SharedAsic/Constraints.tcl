# Same explicit engineering budgets as the previous 150 MHz TT study.
# This top is the synchronous NICE engine. Its reset is driven by the platform.
create_clock -name CoreClock -period 6.666667 [get_ports nice_clk]
set_clock_uncertainty -setup 0.200 [all_clocks]
set_clock_uncertainty -hold 0.100 [all_clocks]
set_clock_transition 0.100 [all_clocks]
foreach_in_collection Port [all_inputs] {
    if {[get_object_name $Port] eq "nice_clk"} {continue}
    set_input_delay -clock [get_clocks CoreClock] -max 1.000 $Port
    set_input_delay -clock [get_clocks CoreClock] -min 0.100 $Port
    set_input_transition 0.100 $Port
}
foreach_in_collection Port [all_outputs] {
    set_output_delay -clock [get_clocks CoreClock] -max 1.000 $Port
    set_output_delay -clock [get_clocks CoreClock] -min -0.100 $Port
    set_load 0.035 $Port
}
# No false path or multicycle exception; CPU<->NICE/ICB are budgeted IO.
if {[sizeof_collection [all_clocks]] != 1} {error "Expected one clock"}
