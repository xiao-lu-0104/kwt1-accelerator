# Inspect block-local startpoints after synthesis without changing constraints.
set root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint [file join $root syn compact_out compact_synth.dcp]
report_timing -from [all_registers] -to [all_registers] -max_paths 10 \
    -file [file join $root syn compact_out timing_core.rpt]
report_timing -from [all_inputs] -to [all_registers] -max_paths 5 \
    -file [file join $root syn compact_out timing_input.rpt]
report_timing -from [all_registers] -to [all_outputs] -max_paths 5 \
    -file [file join $root syn compact_out timing_output.rpt]
foreach {label pattern} {ln *u_ln/* mac *u_mac/* sm *g_sm4.u_sm/*} {
    set regs [get_cells -hierarchical -filter "IS_SEQUENTIAL == 1 && NAME =~ $pattern"]
    if {[llength $regs]} {
        report_timing -from $regs -max_paths 5 -file [file join $root syn hotspots_${label}.rpt]
    }
    if {[llength $regs]} {
        report_timing -to $regs -max_paths 3 -file [file join $root syn hotspots_to_${label}.rpt]
    }
}
set newton [get_cells -hierarchical -regexp {.*u_ln/(inv_r|y0sq_r|vy_r|t3_r)_reg.*}]
report_timing -to $newton -max_paths 3 -file [file join $root syn hotspots_newton.rpt]
set lnmem [get_cells -hierarchical -filter {NAME =~ *u_ln/x_buf*}]
report_timing -to $lnmem -max_paths 3 -file [file join $root syn hotspots_align.rpt]
