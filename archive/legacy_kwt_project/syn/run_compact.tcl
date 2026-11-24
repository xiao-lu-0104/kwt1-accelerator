# FPGA feasibility check for the competition encoder boundary (99x64 in/out).
# This is not the ASIC mm^2 result. ASIC requires KWT_ASIC_SRAM plus a foundry
# adapter, real macro timing/area models and the competition standard-cell lib.
set root [file normalize [file join [file dirname [info script]] ..]]
set kv_shared 1
set softmax_lanes 4
set output_name compact_out
if {[lsearch -exact $argv "-wide-kv"] >= 0} {
    set kv_shared 0
    set output_name compact_wide_out
}
if {[lsearch -exact $argv "-serial-softmax"] >= 0} {
    set softmax_lanes 1
    append output_name _sm1
}
set mode_args {}
if {[lsearch -exact $argv "-ooc"] >= 0} {
    set mode_args [list -mode out_of_context]
    append output_name _ooc
}
set outdir [file join $root syn $output_name]
file mkdir $outdir
read_verilog -sv [glob [file join $root rtl *.v]]
read_xdc [file join $root syn kwt_top.xdc]
synth_design -top kwt_encoder_12 -part xc7a100tfgg484-2 \
    -generic [list KV_SHARED=$kv_shared SOFTMAX_LANES=$softmax_lanes] -flatten_hierarchy rebuilt {*}$mode_args
report_utilization -hierarchical -file [file join $outdir utilization.rpt]
report_timing_summary -file [file join $outdir timing.rpt]
report_timing -max_paths 10 -file [file join $outdir timing_paths.rpt]
report_timing -from [all_registers] -to [all_registers] -max_paths 10 -file [file join $outdir timing_core.rpt]
write_checkpoint -force [file join $outdir compact_synth.dcp]
