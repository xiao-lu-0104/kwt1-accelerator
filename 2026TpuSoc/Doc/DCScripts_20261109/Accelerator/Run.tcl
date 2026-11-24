# Fresh c03eb04 RTL + existing platform ICB; new combination not functionally qualified.
if {[catch {
set Tools $::env(TPU_SHARED_TOOLS)
set Source $::env(TPU_SHARED_SOURCE)
set Out $::env(TPU_ASIC_OUT)
set Top e203_subsys_nice_core
set target_library [list $::env(TPU_STDCELL_DB)]
set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
file mkdir $Out
cd $Out
set_app_var verilogout_no_tri true
set_host_options -max_cores 4
set_svf [file join $Out guidance.svf]
saif_map -start
set_app_var search_path [concat $search_path [list $Source]]
define_design_lib WORK -path [file join $Out work]
source [file join $Source Sources.tcl]
if {![analyze -format sverilog -define {SYNTHESIS TPU_SRAM_MODEL} -library WORK $Sources]} {
    error "RTL analyze failed"
}
elaborate $Top -library WORK
current_design $Top
if {![link]} {error "Initial link failed"}
source [file join $Tools AsicCommon.tcl]
source [file join $Tools HoldPolicy.tcl]
set MacroLib [get_lib_cells -quiet */RAMSP1024X16]
if {[sizeof_collection $MacroLib] != 1} {error "Expected one real SRAM library cell"}
set MacroArea [get_attribute $MacroLib area]
if {abs($MacroArea - 9148.524700) > 0.01} {error "Unexpected reviewed SRAM area"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Expected 56 real private SRAM macros"}
set_dont_touch $Macros true
source [file join $Tools Constraints.tcl]
write_sdc -nosplit [file join $Out before_compile.sdc]
puts "DC_STAGE: compile_start"
if {![compile_ultra -no_autoungroup -no_boundary_optimization]} {error "compile_ultra failed"}
write -hierarchy -format ddc -output [file join $Out baseline.ddc]
write -hierarchy -format verilog -output [file join $Out baseline.v]
write_sdc -nosplit [file join $Out baseline.sdc]
puts "DC_STAGE: baseline_saved"
set BeforeSetup [PathSlack max]
set BeforeHold [PathSlack min]
set BeforeArea [LibraryLeafArea]
report_timing -delay_type max -max_paths 10 -significant_digits 6 > baseline_setup.rpt
report_timing -delay_type min -max_paths 10 -significant_digits 6 > baseline_hold.rpt
set Signature [TimingSignature [file join $Out baseline.sdc]]
set Outside [OutsideReferences]
set Repaired 0
if {$BeforeHold < 0} {
    puts "DC_STAGE: sram_hold_start"
    # One bounded attempt restricted to SRAM; preserve all sibling logic and IO.
    set Scope [get_cells -quiet Tpu/Core/Sram]
    if {[sizeof_collection $Scope] != 1} {error "Missing preserved SRAM hierarchy"}
    set Frozen ""
    foreach_in_collection Cell [get_cells -hierarchical] {
        set Name [get_object_name $Cell]
        if {![InSram $Name] && ![SramAncestor $Name]} {
            set Frozen [add_to_collection $Frozen $Cell]
        }
    }
    set_dont_touch $Frozen true
    set_dont_touch [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}] true
    set_fix_hold [get_clocks CoreClock]
    if {![compile -incremental_mapping -only_hold_time]} {error "Hold-only compile failed"}
    set Repaired 1
}
write -hierarchy -format ddc -output [file join $Out candidate.ddc]
write -hierarchy -format verilog -output [file join $Out candidate.v]
write_sdc -nosplit [file join $Out candidate.sdc]
if {![link]} {error "Candidate link failed"}
if {$Signature ne [TimingSignature [file join $Out candidate.sdc]]} {
    error "Timing requirements changed during hold repair"
}
AssertSameReferences $Outside [OutsideReferences]
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Mapped SRAM count changed"}
foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set Ref [get_attribute $Cell ref_name]
    if {$Ref in {**logic_0** **logic_1**}} {continue}
    if {[sizeof_collection [get_lib_cells -quiet */$Ref]] != 1} {
        error "Unmapped/ambiguous leaf [get_object_name $Cell]: $Ref"
    }
}
report_area -hierarchy > area.rpt
report_units > units.rpt
report_reference -hierarchy > references.rpt
report_qor > qor.rpt
check_design > check_design.rpt
check_timing > check_timing.rpt
report_constraint -all_violators > constraint_violations.rpt
report_timing -delay_type max -max_paths 20 -significant_digits 6 > setup.rpt
report_timing -delay_type min -max_paths 20 -significant_digits 6 > hold.rpt
set Setup [PathSlack max]
set Hold [PathSlack min]
set Area [LibraryLeafArea]
set F [open summary.txt w]
foreach {Key Value} [list TOP $Top SOURCE_ID c03eb048481b7d271dba54e518092c2eb9aa528f_with_platform_icb \
    BOUNDARY "NICE+TPU+DMA+ICB+private SRAM; CPU/shared TCM excluded" \
    CORNER "SMIC40 TT 1.1V 25C; pre-layout engineering budgets" \
    PERIOD_NS 6.666667 SETUP_UNCERTAINTY_NS 0.2 HOLD_UNCERTAINTY_NS 0.1 \
    SRAM_COUNT 56 SRAM_LIBRARY_AREA [expr {56*$MacroArea}] \
    TOTAL_LIBRARY_CELL_AREA $Area LOGIC_LIBRARY_CELL_AREA [expr {$Area-56*$MacroArea}] \
    AREA_METHOD "sum of mapped leaf library-cell areas including private SRAM; see units.rpt" \
    BASELINE_AREA $BeforeArea BASELINE_SETUP_WNS_NS $BeforeSetup BASELINE_HOLD_WNS_NS $BeforeHold \
    HOLD_REPAIR_ATTEMPTED $Repaired OUTSIDE_SRAM_REFERENCES UNCHANGED TIMING_REQUIREMENTS UNCHANGED \
    SETUP_WNS_NS $Setup HOLD_WNS_NS $Hold \
    SETUP_STATUS [expr {$Setup >= 0 ? "PASS" : "FAIL"}] \
    HOLD_STATUS [expr {$Hold >= 0 ? "PASS" : "FAIL"}] \
    POWER_STATUS "PENDING_ACTIVITY_ANNOTATION; no vectorless result claimed" \
    FUNCTIONAL_COMBINATION_STATUS NOT_YET_QUALIFIED NETLIST_SIMULATION_STATUS NOT_RUN \
    ACCEPTANCE "reports only; inspect check_timing/design; no physical/multicorner signoff"] {
    puts "$Key: $Value"
    puts $F "$Key: $Value"
}
close $F
saif_map -write_map [file join $Out name_map.tcl]
set_svf -off
puts "SHARED_ASIC_REPORTS_COMPLETE: $Out"
} Error]} {
    puts stderr "SHARED_ASIC_ERROR: $Error"
    puts stderr $::errorInfo
    exit 1
}
exit 0
