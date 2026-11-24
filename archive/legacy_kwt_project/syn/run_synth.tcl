# ---------------------------------------------------------------------------
# KWT-1 accelerator synthesis / area-timing estimate
#
#   vivado -mode batch -source syn/run_synth.tcl -tclargs <part>
#
# Default part is Artix-7 XC7A100T (the FPGA used during development). When the
# competition standard-cell library arrives, replace the part/library section
# with the matching read_liberty + compile_ultra flow; the file list and the
# top name stay the same.
# ---------------------------------------------------------------------------

set root [file normalize [file join [file dirname [info script]] ..]]
set part "xc7a100tfgg484-2"
if {[llength $argv] > 0} { set part [lindex $argv 0] }

# 设计里有 6~20 万 bit 级的大 reg 数组（p_buf 78440 / score_buf 158400 /
# h_buf 202752 ...），Vivado 默认溶解上限是 78440，超过直接 ERROR 退出。
# 抬高上限让它们溶解成触发器，否则综合根本跑不完。
set_param synth.elaboration.rodinMoreOptions {rt::set_parameter dissolveMemorySizeLimit 400000}

set outdir [file join $root syn out]
file mkdir $outdir

puts "==> part      : $part"
puts "==> rtl root  : $root"
puts "==> output    : $outdir"

# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
set srcs [concat \
    [glob -nocomplain [file join $root rtl *.v]] ]

puts "==> [llength $srcs] RTL files"

read_verilog -sv $srcs
read_xdc [file join $root syn kwt_top.xdc]

# ---------------------------------------------------------------------------
# synthesis
# ---------------------------------------------------------------------------
synth_design -top kwt_top -part $part -flatten_hierarchy none

# 150 MHz target -> 6.667 ns period, 20 % clock uncertainty margin
create_clock -name clk -period 6.667 [get_ports clk]
set_clock_uncertainty 0.6 [get_clocks clk]
set_input_delay  -clock clk 2.0 [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -clock clk 2.0 [all_outputs]
set_load 0.05 [all_outputs]

opt_design

# 1.47M 触发器远超 XC7A100T 的 126,800，place_design 必然失败。
# 默认只跑到 opt_design 出资源/时序报告；加 -impl 才继续走完整实现。
if {[lsearch -exact $argv "-impl"] >= 0} {
    place_design
    route_design
}

# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------
report_utilization          -file [file join $outdir utilization.rpt]
report_timing_summary       -file [file join $outdir timing.rpt] -delay_type max
report_timing -max_paths 20 -file [file join $outdir timing_paths.rpt]
report_power                -file [file join $outdir power.rpt]
report_design_analysis      -file [file join $outdir design_analysis.rpt]

write_checkpoint -force [file join $outdir kwt_top_routed.dcp]

# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
set wns  [get_property SLACK [get_timing_paths -delay_type max]]
set util [report_utilization -return_string]

puts ""
puts "================ SYNTHESIS SUMMARY ================"
puts "part       : $part"
puts "WNS (ns)   : $wns"
if {$wns >= 0} {
    puts "timing     : MET at 150 MHz"
} else {
    set fmax [expr {1000.0 / (6.667 - $wns)}]
    puts [format "timing     : VIOLATED, estimated Fmax = %.1f MHz" $fmax]
}
foreach pat {LUT LUTRAM FF BRAM DSP} {
    if {[regexp "\\| $pat\\s+\\|\\s+(\\d+)" $util -> n]} {
        puts [format "%-10s : %s" $pat $n]
    }
}
puts "reports    : $outdir"
puts "==================================================="
