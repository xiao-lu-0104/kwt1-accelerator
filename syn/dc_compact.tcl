# ---------------------------------------------------------------------------
# KWT-1 encoder ASIC synthesis - SMIC 40nm (SCC40NLL_VHSC40_RVT)
#
#   dc_shell -f syn/dc_compact.tcl | tee syn/dc_compact.log
#
# 顶层 kwt_encoder_12，COMPACT=1，四路 Softmax。
# 目标 150 MHz（周期 6.667 ns，另留 1.0 ns 时钟不确定性）。
# ---------------------------------------------------------------------------

set DESIGN   kwt_encoder_12
set CLK_PER  6.667
set REPORT   ./dc_out

# ---- 库路径（服务器上已解压的位置） ---------------------------------------
# 注意：Tcl 里环境变量是 $::env(HOME)，写成 $env(HOME) 会变成空字符串，
#       target_library 静默失效，DC 回退到 gtech（无面积信息）。这里用绝对路径。
set LIBROOT  /storage1/2026contest/server1/s1_12usr/lib/S40/smic
set STDCELL  $LIBROOT/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1
set LIBDIR   $STDCELL/liberty/1.1v
set SRAMDIR  /storage1/admin_public_dir/SRAM_Lib_2025

if {![file exists $LIBDIR/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db]} {
    puts "ERROR: library db not found at $LIBDIR"
    exit 1
}

file mkdir $REPORT

# ---- 库 -------------------------------------------------------------------
# typical 角用于综合；SS 角用于最终的 setup 分析
set target_library [list \
    $LIBDIR/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db ]

set link_library [concat "*" $target_library]

# SRAM 宏走黑盒路线（见下方 analyze 的 -define），这里不读 SRAM 的 lib/db。
# 拿到 SRAM_Lib_2025 里各宏的 tt 角后，可把 .db 加进 target_library 并用真实
# 宏替换 kwt_foundry_sram16，那时 SRAM 的时序和面积会自动进报告。

# ---- 源码 -----------------------------------------------------------------
set RTL [glob ./rtl/*.v]
set_app_var verilogout_no_tri true
define_design_lib WORK -path $REPORT/work

# 关键：定义 KWT_ASIC_SRAM，让 kwt_mem16 走 kwt_foundry_sram16 宏实例分支，
# 而不是 reg [15:0] mem[0:DEPTH-1] 行为数组。那个模块不在 RTL 里，link 会
# 自动建成黑盒（面积 0），SRAM 的真实面积和访问延迟另外补。
#
# 教训：之前用 set_dont_touch [get_designs kwt_mem16] 完全挡不住 ——
# kwt_packed_sram 把内存按 16 位 bank 展开成 101 个参数化实例，design 名
# 根本不叫 kwt_mem16，结果 786,432 bit 全被映射成 615,938 个触发器，
# 面积虚高到 5.10 mm^2，还白跑了 3 小时。
analyze -format sverilog -define KWT_ASIC_SRAM -library WORK $RTL
elaborate $DESIGN -library WORK -architecture verilog
current_design $DESIGN

link

set _sram [get_cells -hierarchical -filter "ref_name =~ kwt_foundry_sram16*"]
puts " INFO      : SRAM black boxes = [sizeof_collection $_sram]"

# ---- 约束 -----------------------------------------------------------------
create_clock -name clk -period $CLK_PER [get_ports clk]
set_clock_uncertainty 1.0 [get_clocks clk]
set_clock_transition  0.2 [get_clocks clk]

# 输入/输出延迟：加速器内部到 SRAM 的信号按 0.5 ns 估
set_input_delay  -clock clk 0.5 [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -clock clk 0.5 [all_outputs]
set_load 0.02 [all_outputs]

# 黑盒没有时序模型，不给边界延迟的话穿越 SRAM 的路径会被当成 0 延迟，
# WNS 会严重偏乐观。按 40nm 1024x16 宏的典型值补上。
if {[sizeof_collection $_sram] > 0} {
    catch {set_output_delay -clock clk 1.2 [get_pins -of_objects $_sram -filter "direction == out"]}
    catch {set_input_delay  -clock clk 0.3 [get_pins -of_objects $_sram -filter "direction == in"]}
    puts " INFO      : SRAM modeled as 1.2 ns access / 0.3 ns setup"
}

# 不用 set_max_area 0：它会逼 DC 无限逼近最小面积，实测把综合时间从
# 分钟级拉长到 3 小时以上，面积收益不到 2%。用默认 area effort。

# ---- 综合 -----------------------------------------------------------------
compile_ultra -no_autoungroup

# ---- 报告 -----------------------------------------------------------------
report_qor                        > $REPORT/qor.rpt
report_area -hierarchy            > $REPORT/area.rpt
report_area                       > $REPORT/area_total.rpt
report_timing -max_paths 20 -delay_type max > $REPORT/timing_max.rpt
report_timing -max_paths 10 -delay_type min > $REPORT/timing_min.rpt
report_power                      > $REPORT/power.rpt
report_clock_gating               > $REPORT/clock_gating.rpt
report_constraint -all_violators   > $REPORT/violators.rpt
check_design                      > $REPORT/check_design.rpt

# ---- 输出 -----------------------------------------------------------------
write -hierarchy -format verilog -output $REPORT/${DESIGN}_netlist.v
write_sdc -nosplit $REPORT/${DESIGN}.sdc
write_sdf -version 3.0 $REPORT/${DESIGN}.sdf
write -hierarchy -format ddc -output $REPORT/${DESIGN}.ddc

# ---- 摘要 -----------------------------------------------------------------
# 坑：get_attribute [current_design] area 实测返回空串（上一轮就是这样把面积
# 打成 <unavailable> 的）。直接从 area_total.rpt 里正则抠数字最稳。
set area ""
set nff  ""
if {[file exists $REPORT/area_total.rpt]} {
    set fp [open $REPORT/area_total.rpt r]
    set txt [read $fp]
    close $fp
    regexp {Total cell area:\s+([0-9.]+)}         $txt -> area
    regexp {Number of sequential cells:\s+([0-9]+)} $txt -> nff
}
if {$area eq ""} { set area [get_attribute [current_design] area] }
set wns [get_attribute [get_timing_paths -delay_type max] slack]
puts "=================================================="
puts " DESIGN    : $DESIGN"
puts " LIBRARY   : SCC40NLL_VHSC40_RVT  tt_v1p1_25c_ccs"
puts " PERIOD    : $CLK_PER ns  (150 MHz target)"
puts " SEQ CELLS : $nff   (逻辑触发器，正常应 ~2e4；若 >5e5 说明 SRAM 又被展开了)"
if {$area eq ""} {
    puts " AREA      : <unavailable>"
} else {
    puts [format " AREA      : %.2f um^2  (%.4f mm^2)   不含 SRAM 宏" $area [expr {$area / 1.0e6}]]
}
if {$wns eq ""} {
    puts " WNS       : <unavailable>"
} else {
    puts [format " WNS       : %.3f ns" $wns]
}
puts " REPORTS   : $REPORT"
puts "=================================================="
exit
