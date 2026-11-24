# One shared clock, engineering budgets identical to the preceding ASIC run.
create_clock -name CoreClock -period 6.666667 [get_ports Clock]
set_clock_uncertainty -setup 0.200 [all_clocks]
set_clock_uncertainty -hold 0.100 [all_clocks]
set_clock_transition 0.100 [all_clocks]
if {$Top eq "E203TpuBackend"} {
    # The new wrapper synchronizes release once for the complete common domain.
    set_false_path -from [get_ports ResetN]
}
foreach_in_collection Port [all_inputs] {
    set Name [get_object_name $Port]
    if {$Name eq "Clock"} {continue}
    if {$Name eq "CpuClock"} {error "Unexpected second clock in single-clock backend"}
    if {$Name eq "ResetN" && $Top eq "E203TpuBackend"} {continue}
    set_input_delay -clock [get_clocks CoreClock] -max 1.000 $Port
    set_input_delay -clock [get_clocks CoreClock] -min 0.100 $Port
    set_input_transition 0.100 $Port
}
foreach_in_collection Port [all_outputs] {
    set_output_delay -clock [get_clocks CoreClock] -max 1.000 $Port
    set_output_delay -clock [get_clocks CoreClock] -min -0.100 $Port
    set_load 0.035 $Port
}
puts "CLOCK_PROFILE: common CoreClock 150MHz, direct synchronous NICE"
puts "CONSTRAINT_PROFILE: engineering setup/hold uncertainty=0.2/0.1ns; no CDC exceptions"
