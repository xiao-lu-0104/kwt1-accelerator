# Read-only baseline/candidate inspection. No synthesis or netlist edits.
if {[catch {
set Tools $::env(TPU_HOLD_TOOLS)
set Out $::env(TPU_ASIC_OUT)
set Mode $::env(TPU_HOLD_VIEW)
set Top E203TpuBackend
set target_library [list $::env(TPU_STDCELL_DB)]
set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
file mkdir $Out
cd $Out
read_ddc $::env(TPU_HOLD_DDC)
current_design $Top
if {![link]} {error "Checkpoint link failed"}
source [file join $Tools AsicCommon.tcl]
source [file join $Tools HoldPolicy.tcl]
set Clock [get_clocks -quiet CoreClock]
if {[sizeof_collection [all_clocks]] != 1 || [sizeof_collection $Clock] != 1} {error "Expected one CoreClock"}
if {abs([get_attribute $Clock period] - 6.666667) > 0.000001} {error "Expected 150MHz"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Expected 56 SRAM macros"}
set Lib [get_lib_cells -quiet */RAMSP1024X16]
if {[sizeof_collection $Lib] != 1} {error "Missing SRAM library"}
set MacroArea [get_attribute $Lib area]
if {abs($MacroArea-9148.524700) > 0.01} {error "Unexpected SRAM library area"}
set Pins [get_pins -of_objects $Macros -filter {direction == in && full_name !~ */CLK}]
if {![sizeof_collection $Pins]} {error "Missing SRAM inputs"}
set Setup [PathSlack max]
set Hold [PathSlack min]
set SramHold [PathSlack min -to $Pins]
set Area [LibraryLeafArea]
set F [open [file join $Out metrics.tsv] w]
foreach {Key Value} [list SETUP_WNS_NS $Setup HOLD_WNS_NS $Hold SRAM_INPUT_HOLD_WNS_NS $SramHold AREA $Area] {
    puts $F "$Key\t$Value"
    puts "${Mode}_${Key}: $Value"
}
close $F
set F [open [file join $Out outside_cells.tsv] w]
dict for {Name Ref} [OutsideReferences] {puts $F "$Name\t$Ref"}
close $F
write_sdc -nosplit [file join $Out snapshot.sdc]
set F [open [file join $Out timing_signature.txt] w]
foreach Line [TimingSignature [file join $Out snapshot.sdc]] {puts $F $Line}
close $F
if {$Mode eq "CANDIDATE"} {
    # Generate all diagnostics before judging outside-SRAM differences.
    source [file join $Tools Reports.tcl]
    report_timing -delay_type min -to $Pins -max_paths 10 -significant_digits 6 > [file join $Out sram_input_hold.rpt]
}
puts "HOLD_SNAPSHOT_COMPLETE: $Mode $Out"
} Error]} {
    puts stderr "HOLD_REPORT_ERROR: $Error"
    exit 1
}
exit 0
