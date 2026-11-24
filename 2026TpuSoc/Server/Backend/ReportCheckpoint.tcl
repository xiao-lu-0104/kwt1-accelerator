# Read-only netlist recovery: NO analyze/elaborate/compile/optimization.
if {[catch {
set Top $::env(TPU_ASIC_TOP)
set Out $::env(TPU_ASIC_OUT)
set Tools $::env(TPU_REPORT_TOOLS)
set Checkpoint $::env(TPU_REPORT_DDC)
set StdDb $::env(TPU_STDCELL_DB)
set SpDb $::env(TPU_SRAM_DB)
if {$Top ni {TpuNiceAxi E203Tpu}} {error "Unsupported checkpoint top"}
foreach Input [list $Checkpoint $StdDb $SpDb] {
    if {![file isfile $Input]} {error "Missing checkpoint/library input: $Input"}
}
file mkdir $Out
cd $Out
set target_library [list $StdDb]
set link_library [concat [list *] $target_library [list $SpDb]]
if {![read_ddc $Checkpoint]} {error "Cannot read mapped checkpoint"}
current_design $Top
if {![link]} {error "Checkpoint link failed"}
source [file join $Tools AsicCommon.tcl]
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Checkpoint does not contain 56 real SRAM macros"}
set Lib [get_lib_cells -quiet */RAMSP1024X16]
if {[sizeof_collection $Lib] != 1} {error "Missing or ambiguous SRAM library"}
set MacroArea [get_attribute $Lib area]
if {abs($MacroArea-9148.524700) > 0.01} {error "Wrong SRAM library area"}
set ExpectedClocks 1
if {$Top eq "E203Tpu"} {set ExpectedClocks 2}
if {[sizeof_collection [all_clocks]] != $ExpectedClocks} {error "Unexpected clock count"}
foreach Name {TpuClock CpuClock} {
    if {$Name eq "CpuClock" && $Top ne "E203Tpu"} {continue}
    set Clk [get_clocks -quiet $Name]
    if {[sizeof_collection $Clk] != 1} {error "Missing clock $Name"}
    set Period [get_attribute $Clk period]
    if {![string is double -strict $Period] || abs($Period-6.666667) > 0.000001} {
        error "Checkpoint $Name is not the expected 150MHz profile"
    }
}
set CpuPeriod 6.666667
write_sdc -nosplit [file join $Out checkpoint_loaded.sdc]
set Frozen [FrozenBudgetSignature [file join $Out checkpoint_loaded.sdc]]
if {$Top eq "E203Tpu"} {
    # Same receive-domain budgets as synthesis, now encoded with actual CP/D
    # pins. No RTL, mapped cell, clock, IO or uncertainty change is made.
    source [file join $Tools AsicCdc.tcl]
}
write_sdc -nosplit [file join $Out report_view.sdc]
if {$Frozen ne [FrozenBudgetSignature [file join $Out report_view.sdc]]} {
    error "Clock/uncertainty/IO budget changed during report recovery"
}
report_clock > [file join $Out clocks.rpt]
set ReportView "mapped checkpoint; corrected numeric reduction/area and explicit CDC CP-to-D endpoints; no reoptimization"
source [file join $Tools AsicReports.tcl]
puts "CHECKPOINT_REPORT_COMPLETE: $Out"
} Error]} {
    puts stderr "ASIC_REPORT_ERROR: $Error"
    exit 1
}
exit 0
