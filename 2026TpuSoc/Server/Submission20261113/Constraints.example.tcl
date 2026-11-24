# Copy into NEW source configuration and review actual ports before binding.
# Budgets follow the previous SMIC40 TT study. Do not hide paths with exceptions.
create_clock -name CoreClock -period 6.666667 [get_ports $ClockPort]
set_clock_uncertainty -setup 0.200 [all_clocks]
set_clock_uncertainty -hold 0.100 [all_clocks]
set_clock_transition 0.100 [all_clocks]
# Add real forwarded/generated clocks before setting output budgets. Forwarded
# clock outputs must be excluded from data output_delay, as in the earlier study.
foreach_in_collection P [all_inputs] {
    if {[get_object_name $P] eq $ClockPort} {continue}
    set_input_delay -clock CoreClock -max 1.000 $P
    set_input_delay -clock CoreClock -min 0.100 $P
    set_input_transition 0.100 $P
}
foreach_in_collection P [all_outputs] {
    set_output_delay -clock CoreClock -max 1.000 $P
    set_output_delay -clock CoreClock -min -0.100 $P
    set_load 0.035 $P
}
