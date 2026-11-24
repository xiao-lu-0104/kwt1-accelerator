# Same declared engineering IO budgets as the previous SMIC40 study.
# This scoring boundary has a single synchronous clock and no forwarded clocks.
create_clock -name CoreClock -period 6.666667 [get_ports Clock]
set_clock_uncertainty -setup 0.200 [all_clocks]
set_clock_uncertainty -hold 0.100 [all_clocks]
set_clock_transition 0.100 [all_clocks]
foreach_in_collection P [all_inputs] {
    if {[get_object_name $P] eq "Clock"} {continue}
    set_input_delay -clock CoreClock -max 1.000 $P
    set_input_delay -clock CoreClock -min 0.100 $P
    set_input_transition 0.100 $P
}
foreach_in_collection P [all_outputs] {
    set_output_delay -clock CoreClock -max 1.000 $P
    set_output_delay -clock CoreClock -min -0.100 $P
    set_load 0.035 $P
}
