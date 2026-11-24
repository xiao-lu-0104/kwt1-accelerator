# Single-clock 88e529e SMIC40 TT synthesis; no CDC exceptions or repair loop.
if {[catch {
set Root $::env(TPU_ASIC_ROOT)
set Out $::env(TPU_ASIC_OUT)
set Top $::env(TPU_ASIC_TOP)
set StdDb $::env(TPU_STDCELL_DB)
set SpDb $::env(TPU_SRAM_DB)
if {$Top ni {TpuNiceAxi E203TpuBackend}} {error "Unsupported ASIC top"}
foreach Path [list $StdDb $SpDb] {
    if {![file isfile $Path]} {error "Missing library: $Path"}
}
file mkdir $Out
cd $Out
set target_library [list $StdDb]
set link_library [concat [list *] $target_library [list $SpDb]]
set_app_var verilogout_no_tri true
set_app_var search_path [concat $search_path [list [file join $Root Rtl] [file join $Root e203_hbirdv2 rtl e203 core]]]
define_design_lib WORK -path [file join $Out work]
set Sources {}
foreach Name {TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer TpuMatmul TpuGelu TpuVector TpuDma TpuTop TpuNice TpuAxi TpuNiceAxi} {
    lappend Sources [file join $Root Rtl ${Name}.sv]
}
lappend Sources [file join $Root Server Backend SpFoundry.sv]
if {$Top eq "E203TpuBackend"} {
    lappend Sources [file join $Root Rtl TpuResetSync.sv]
    lappend Sources [file join $Root Backend E203TpuBackend.sv]
    foreach Folder {core general} {
        set Sources [concat $Sources [lsort [glob [file join $Root e203_hbirdv2 rtl e203 $Folder *.v]]]]
    }
}
# Do not analyze the generic SRAM model or vendor behavioral implementation.
# The macro reference links directly to the reviewed, freshly converted DB.
if {![analyze -format sverilog -define {SYNTHESIS TPU_SRAM_MODEL} -library WORK $Sources]} {
    error "RTL analyze failed"
}
elaborate $Top -library WORK
current_design $Top
if {![link]} {error "Initial link failed"}
set MacroLib [get_lib_cells -quiet */RAMSP1024X16]
if {[sizeof_collection $MacroLib] != 1} {error "Expected exactly one RAMSP1024X16 library cell"}
set MacroArea [get_attribute $MacroLib area]
if {abs($MacroArea - 9148.524700) > 0.01} {error "SRAM DB area differs from reviewed TT Liberty"}
if {[sizeof_collection [get_lib_pins -quiet */RAMSP1024X16/CLK]] != 1} {error "Missing SRAM library clock"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Expected 56 real SRAM macros before compile"}
set_dont_touch $Macros true

source [file join $Root Server Backend AsicCommon.tcl]
source [file join $Root Server SingleClock Constraints.tcl]
write_sdc -nosplit [file join $Out before_compile.sdc]
check_design > [file join $Out check_design_before.rpt]
check_timing > [file join $Out check_timing_before.rpt]
if {![compile_ultra -no_autoungroup -no_boundary_optimization]} {error "compile_ultra failed"}
# Save the mapped design first; optional/reporting failures need not recompile.
write -hierarchy -format ddc -output [file join $Out ${Top}_mapped.ddc]
write -hierarchy -format verilog -output [file join $Out ${Top}_mapped.v]
write_sdc -nosplit [file join $Out ${Top}_mapped.sdc]
if {![link]} {error "Post-compile link failed"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Real SRAM count changed during compile"}
foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set Ref [get_attribute $Cell ref_name]
    if {$Ref in {**logic_0** **logic_1**}} {continue}
    if {[sizeof_collection [get_lib_cells -quiet */$Ref]] != 1} {
        error "Unmapped/ambiguous leaf [get_object_name $Cell]: $Ref"
    }
}
source [file join $Root Server SingleClock Reports.tcl]
} Error]} {
    puts stderr "ASIC_ERROR: $Error"
    exit 1
}
exit 0
