# ---------------------------------------------------------------------------
# Fast synthesis-only pass (no place & route). Useful during development to
# track area growth; run run_synth.tcl for a full timing-closed estimate.
#
#   vivado -mode batch -source syn/run_synth_only.tcl
# ---------------------------------------------------------------------------

set root [file normalize [file join [file dirname [info script]] ..]]
set part "xc7a100tfgg484-2"
set outdir [file join $root syn out]
file mkdir $outdir

set srcs [glob -nocomplain [file join $root rtl *.v]]
puts "==> [llength $srcs] RTL files, part $part"

read_verilog -sv $srcs
# keep the hierarchy: flattening a design with ~40 KB of register-file arrays
# makes synth_design run for tens of minutes without giving better numbers
synth_design -top kwt_top -part $part -flatten_hierarchy none \
             -directive runtimeoptimized

create_clock -name clk -period 6.667 [get_ports clk]

report_utilization    -file [file join $outdir utilization_synth.rpt]
report_timing_summary -file [file join $outdir timing_synth.rpt]

set util [report_utilization -return_string]
puts ""
puts "============ SYNTH-ONLY SUMMARY ============"
foreach pat {LUT LUTRAM FF BRAM DSP} {
    if {[regexp "\\| $pat\\s+\\|\\s+(\\d+)" $util -> n]} {
        puts [format "%-8s : %s" $pat $n]
    }
}
if {[regexp "\\| Slice LUTs\\s+\\|\\s+(\\d+)" $util -> n]} {
    puts "SliceLUTs : $n"
}
puts "============================================"
