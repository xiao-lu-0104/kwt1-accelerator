# 707cd7f recovery: load saved baseline; no analyze/elaborate/compile_ultra.
if {[catch {
set Tools $::env(TPU_SHARED_TOOLS)
set Input $::env(TPU_RECOVERY_INPUT)
set Out $::env(TPU_ASIC_OUT)
set Top e203_subsys_nice_core
set target_library [list $::env(TPU_STDCELL_DB)]
set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
cd $Out
set_app_var verilogout_no_tri true
set_host_options -max_cores 4
set_svf [file join $Out guidance.svf]
saif_map -start
source [file join $Tools AsicCommon.tcl]
source [file join $Tools HoldPolicy.tcl]
puts "DC_STAGE: recovery_read_baseline"
read_ddc [file join $Input baseline.ddc]
current_design $Top
if {[get_object_name [current_design]] ne $Top} {error "Unexpected loaded top"}
if {![link]} {error "Recovered baseline link failed"}
set MacroLib [get_lib_cells -quiet */RAMSP1024X16]
if {[sizeof_collection $MacroLib] != 1} {error "Expected one real SRAM library cell"}
set MacroArea [get_attribute $MacroLib area]
if {abs($MacroArea - 9148.524700) > 0.01} {error "Unexpected reviewed SRAM area"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Recovered baseline SRAM count mismatch"}
if {[sizeof_collection [all_clocks]] != 1 || [sizeof_collection [get_clocks -quiet CoreClock]] != 1} {
    error "Recovered baseline clocks mismatch"
}
write_sdc -nosplit [file join $Out reload_baseline.sdc]
if {[TimingSignature [file join $Input baseline.sdc]] ne [TimingSignature [file join $Out reload_baseline.sdc]]} {
    error "Saved baseline timing requirements differ after native reload"
}
set F [open baseline_leaves.tsv w]
foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set Ref [get_attribute $Cell ref_name]
    if {$Ref ni {**logic_0** **logic_1**} && [sizeof_collection [get_lib_cells -quiet */$Ref]] != 1} {
        error "Recovered baseline unmapped/ambiguous leaf [get_object_name $Cell]: $Ref"
    }
    puts $F "[get_object_name $Cell]\t$Ref"
}
close $F
set F [open ReloadBaselineSummary.txt w]
foreach {Key Value} [list TOP $Top SOURCE_ID 707cd7f4a0a4d416d11bac71112980079e0a9d34 \
    SRAM_COUNT [sizeof_collection $Macros] BASELINE_SETUP_WNS_NS [PathSlack max] \
    BASELINE_HOLD_WNS_NS [PathSlack min] BASELINE_LIBRARY_AREA [LibraryLeafArea] \
    CLOCK_PERIOD_NATIVE [get_attribute [get_clocks CoreClock] period] TIMING_REQUIREMENTS RELOAD_UNCHANGED] {
    puts $F "$Key: $Value"
    puts "$Key: $Value"
}
close $F
puts "DC_STAGE: recovery_baseline_validated"
set BeforeSetup [PathSlack max]
set BeforeHold [PathSlack min]
set BeforeArea [LibraryLeafArea]
report_timing -delay_type max -max_paths 10 -significant_digits 6 > baseline_setup.rpt
report_timing -delay_type min -max_paths 10 -significant_digits 6 > baseline_hold.rpt
set Signature [TimingSignature [file join $Input baseline.sdc]]
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
puts "DC_STAGE: recovery_candidate_saved"
if {![link]} {error "Candidate link failed"}
if {$Signature ne [TimingSignature [file join $Out candidate.sdc]]} {
    error "Timing requirements changed during hold repair"
}
# Preserve the protection, but save diagnostics even if native hold buffering
# escapes the intended scope. A changed scope quarantines the candidate.
set ScopeStatus UNCHANGED
if {[catch {AssertSameReferences $Outside [OutsideReferences]} ScopeError]} {
    set ScopeStatus REVIEW_REQUIRED
    set F [open outside_scope_error.txt w]; puts $F $ScopeError; close $F
}
set F [open outside_before.tsv w]
dict for {Name Ref} $Outside {puts $F "$Name\t$Ref"}
close $F
set F [open outside_after.tsv w]
dict for {Name Ref} [OutsideReferences] {puts $F "$Name\t$Ref"}
close $F
set F [open candidate_leaves.tsv w]
foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    puts $F "[get_object_name $Cell]\t[get_attribute $Cell ref_name]"
}
close $F
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
foreach {Key Value} [list TOP $Top SOURCE_ID 707cd7f4a0a4d416d11bac71112980079e0a9d34_with_platform_icb \
    BOUNDARY "NICE+TPU+DMA+ICB+private SRAM; CPU/shared TCM excluded" \
    CORNER "SMIC40 TT 1.1V 25C; pre-layout engineering budgets" \
    PERIOD_NS 6.666667 SETUP_UNCERTAINTY_NS 0.2 HOLD_UNCERTAINTY_NS 0.1 \
    SRAM_COUNT 56 SRAM_LIBRARY_AREA [expr {56*$MacroArea}] \
    TOTAL_LIBRARY_CELL_AREA $Area LOGIC_LIBRARY_CELL_AREA [expr {$Area-56*$MacroArea}] \
    AREA_METHOD "sum of mapped leaf library-cell areas including private SRAM; see units.rpt" \
    BASELINE_AREA $BeforeArea BASELINE_SETUP_WNS_NS $BeforeSetup BASELINE_HOLD_WNS_NS $BeforeHold \
    HOLD_REPAIR_ATTEMPTED $Repaired OUTSIDE_SRAM_REFERENCES $ScopeStatus TIMING_REQUIREMENTS UNCHANGED \
    SETUP_WNS_NS $Setup HOLD_WNS_NS $Hold \
    SETUP_STATUS [expr {$Setup >= 0 ? "PASS" : "FAIL"}] \
    HOLD_STATUS [expr {$Hold >= 0 ? "PASS" : "FAIL"}] \
    POWER_STATUS "PENDING_ACTIVITY_ANNOTATION; no vectorless result claimed" \
    FUNCTIONAL_COMBINATION_STATUS NOT_YET_QUALIFIED NETLIST_SIMULATION_STATUS NOT_RUN \
    ACCEPTANCE "QUARANTINED_PENDING_NATIVE_CHECKS_AND_HOLD_CHANGE_REVIEW; not authorized as system input"] {
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
