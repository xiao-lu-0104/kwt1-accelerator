# One bounded hold-only incremental compile of a private mapped checkpoint.
if {[catch {
set Tools $::env(TPU_HOLD_TOOLS)
set Out $::env(TPU_ASIC_OUT)
set Top E203TpuBackend
set target_library [list $::env(TPU_STDCELL_DB)]
set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
file mkdir $Out
cd $Out
read_ddc $::env(TPU_HOLD_DDC)
current_design $Top
if {![link]} {error "Mapped checkpoint link failed"}
source [file join $Tools AsicCommon.tcl]
source [file join $Tools HoldPolicy.tcl]
set Clock [get_clocks -quiet CoreClock]
if {[sizeof_collection [all_clocks]] != 1 || [sizeof_collection $Clock] != 1} {
    error "Expected exactly one CoreClock"
}
if {abs([get_attribute $Clock period] - 6.666667) > 0.000001} {error "Expected 150MHz checkpoint"}
set Scope ""
foreach_in_collection Cell [get_cells -hierarchical] {
    if {[get_object_name $Cell] eq "Tpu/Core/Sram"} {set Scope $Cell}
}
if {[sizeof_collection $Scope] != 1} {error "Missing preserved Tpu/Core/Sram hierarchy"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Expected 56 SRAM macros"}
set MacroLib [get_lib_cells -quiet */RAMSP1024X16]
if {[sizeof_collection $MacroLib] != 1} {error "Missing SRAM library cell"}
set MacroArea [get_attribute $MacroLib area]
if {abs($MacroArea - 9148.524700) > 0.01} {error "Unexpected SRAM library"}
set MacroInputs [get_pins -of_objects $Macros -filter {direction == in && full_name !~ */CLK}]
if {![sizeof_collection $MacroInputs]} {error "Missing SRAM data/control input pins"}
set BeforeSetup [PathSlack max]
set BeforeHold [PathSlack min]
set BeforeSramHold [PathSlack min -to $MacroInputs]
set BeforeArea [LibraryLeafArea]
write_sdc -nosplit [file join $Out before.sdc]
set Signature [TimingSignature [file join $Out before.sdc]]
set Outside [OutsideReferences]
puts "BEFORE_SETUP_WNS_NS: $BeforeSetup"
puts "BEFORE_HOLD_WNS_NS: $BeforeHold"
puts "BEFORE_SRAM_INPUT_HOLD_WNS_NS: $BeforeSramHold"
report_timing -delay_type min -to $MacroInputs -max_paths 10 -significant_digits 6 > [file join $Out before_sram_hold.rpt]

# Freeze sibling hierarchies and every leaf outside SRAM. Do not freeze SRAM
# ancestors (Tpu/Core) as that would implicitly freeze the repair scope too.
set Frozen ""
foreach_in_collection Cell [get_cells -hierarchical] {
    set Name [get_object_name $Cell]
    if {![InSram $Name] && ![SramAncestor $Name]} {set Frozen [add_to_collection $Frozen $Cell]}
}
set_dont_touch $Frozen true
set_dont_touch $Macros true
puts "HOLD_REPAIR_SCOPE: Tpu/Core/Sram; other hierarchies and leaves frozen"
puts "HOLD_REPAIR_MODE: one compile -incremental_mapping -only_hold_time; original timing budgets retained"
set_fix_hold $Clock
if {![compile -incremental_mapping -only_hold_time]} {error "Hold-only incremental compile failed"}

# Save candidate even if acceptance checks or reporting fail later.
write -hierarchy -format ddc -output [file join $Out ${Top}_hold_candidate.ddc]
write -hierarchy -format verilog -output [file join $Out ${Top}_hold_candidate.v]
write_sdc -nosplit [file join $Out ${Top}_hold_candidate.sdc]
if {![link]} {error "Candidate link failed"}
if {$Signature ne [TimingSignature [file join $Out ${Top}_hold_candidate.sdc]]} {
    error "Timing requirements changed; candidate rejected"
}
AssertSameReferences $Outside [OutsideReferences]
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "SRAM count changed"}
puts "OUTSIDE_SRAM_REFERENCES: UNCHANGED"
puts "TIMING_REQUIREMENTS: UNCHANGED"
source [file join $Tools Reports.tcl]
set AfterSramHold [PathSlack min -to [get_pins -of_objects $Macros -filter {direction == in && full_name !~ */CLK}]]
set F [open [file join $Out hold_result.txt] w]
foreach {Key Value} [list BEFORE_SETUP_WNS_NS $BeforeSetup BEFORE_HOLD_WNS_NS $BeforeHold \
    AFTER_SETUP_WNS_NS $Setup AFTER_HOLD_WNS_NS $Hold \
    BEFORE_SRAM_HOLD_WNS_NS $BeforeSramHold AFTER_SRAM_HOLD_WNS_NS $AfterSramHold \
    BEFORE_AREA $BeforeArea AFTER_AREA [LibraryLeafArea]] {
    puts "$Key: $Value"
    puts $F "$Key: $Value"
}
set Status "FAIL"
if {$Setup >= 0 && $Hold >= 0 && $AfterSramHold >= 0} {set Status "PASS"}
puts "HOLD_REPAIR_STATUS: $Status (TT pre-layout only)"
puts $F "HOLD_REPAIR_STATUS: $Status (TT pre-layout only)"
close $F
puts "HOLD_REPAIR_REPORTS_COMPLETE: $Out"
} Error]} {
    puts stderr "HOLD_REPAIR_ERROR: $Error"
    exit 1
}
exit 0
