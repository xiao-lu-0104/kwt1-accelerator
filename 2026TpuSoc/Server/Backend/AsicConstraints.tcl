# Initial independent ASIC engineering budget, not an official competition SDC.
# All values are ns except the output load in the loaded library's capacitance unit.
create_clock -name TpuClock -period 6.666667 [get_ports Clock]
if {$Top eq "E203Tpu"} {
    create_clock -name CpuClock -period $CpuPeriod [get_ports CpuClock]
}
set_clock_uncertainty -setup 0.200 [all_clocks]
set_clock_uncertainty -hold 0.100 [all_clocks]
set_clock_transition 0.100 [all_clocks]
if {$Top eq "E203Tpu"} {
    # Integrated top has explicit per-domain asynchronous reset synchronizers.
    set_false_path -from [get_ports ResetN]
}

# Constrain each external interface in its own domain. These are explicit
# provisional integration budgets; report internal paths separately as well.
foreach_in_collection Port [all_inputs] {
    set Name [get_object_name $Port]
    if {$Name in {Clock CpuClock}} {continue}
    if {$Name eq "ResetN" && $Top eq "E203Tpu"} {continue}
    set Domain TpuClock
    if {$Top eq "E203Tpu" && ![string match Axi* $Name]} {set Domain CpuClock}
    set_input_delay -clock [get_clocks $Domain] -max 1.000 $Port
    set_input_delay -clock [get_clocks $Domain] -min 0.100 $Port
    set_input_transition 0.100 $Port
}
foreach_in_collection Port [all_outputs] {
    set Name [get_object_name $Port]
    set Domain TpuClock
    if {$Top eq "E203Tpu" && ![string match Axi* $Name]} {set Domain CpuClock}
    set_output_delay -clock [get_clocks $Domain] -max 1.000 $Port
    set_output_delay -clock [get_clocks $Domain] -min -0.100 $Port
    set_load 0.035 $Port
}

puts "CONSTRAINT_PROFILE: engineering assumptions; setup_uncertainty=0.2 ns; hold_uncertainty=0.1 ns"
puts "IO_BUDGET: max=1 ns; input_min=0.1 ns; output_min=-0.1 ns; transition=0.1 ns; load=0.035 library units"
