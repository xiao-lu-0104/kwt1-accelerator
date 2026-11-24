# Reporting only. Requires the mapped design, libraries and Common helpers.
report_area -hierarchy > [file join $Out area.rpt]
report_qor > [file join $Out qor.rpt]
report_reference -hierarchy > [file join $Out references.rpt]
report_units > [file join $Out units.rpt]
check_design > [file join $Out check_design.rpt]
check_timing > [file join $Out check_timing.rpt]
report_constraint -all_violators > [file join $Out constraints_violations.rpt]
report_timing -delay_type max -max_paths 20 -significant_digits 6 > [file join $Out setup.rpt]
report_timing -delay_type min -max_paths 20 -significant_digits 6 > [file join $Out hold.rpt]
set Summary [open [file join $Out summary.txt] w]
proc Emit {Key Value} {
    global Summary
    puts "$Key: $Value"
    puts $Summary "$Key: $Value"
}
Emit TOP $Top
if {[info exists ReportView]} {Emit REPORT_VIEW $ReportView}
Emit CORNER "SMIC40 standard cells + RAMSP1024X16; TT 1.1V 25C; pre-layout synthesis"
Emit TPU_PERIOD_NS 6.666667
if {$Top eq "E203Tpu"} {Emit CPU_PERIOD_NS $CpuPeriod}
Emit CONSTRAINT_STATUS "PROVISIONAL_ENGINEERING_BUDGET; not official/signoff"
Emit SETUP_UNCERTAINTY_NS 0.200
Emit HOLD_UNCERTAINTY_NS 0.100
Emit SRAM_CELLS "56 x RAMSP1024X16; 112 KiB"
Emit SRAM_LIBRARY_AREA [expr {56 * $MacroArea}]
Emit TOTAL_LIBRARY_CELL_AREA [LibraryLeafArea]
Emit AREA_METHOD "sum of mapped leaf library-cell areas, including 56 SRAM macros"
set GlobalSetup [PathSlack max]
set GlobalHold [PathSlack min]
Emit SETUP_WNS_NS $GlobalSetup
Emit HOLD_WNS_NS $GlobalHold
Emit SETUP_STATUS [expr {$GlobalSetup >= 0 ? "PASS" : "FAIL"}]
Emit HOLD_STATUS [expr {$GlobalHold >= 0 ? "PASS" : "FAIL"}]
set Groups {TpuClock}
if {$Top eq "E203Tpu"} {lappend Groups CpuClock}
foreach Group $Groups {
    Emit ${Group}_SETUP_WNS_NS [PathSlack max -group $Group]
    Emit ${Group}_HOLD_WNS_NS [PathSlack min -group $Group]
    report_timing -group $Group -delay_type max -max_paths 10 -significant_digits 6 > [file join $Out ${Group}_setup.rpt]
    report_timing -group $Group -delay_type min -max_paths 10 -significant_digits 6 > [file join $Out ${Group}_hold.rpt]
    # Registers include SRAM data/control pins; exclude asynchronous CDC sources
    # with an explicit launch/capture domain filter, not a broad path cut.
    set Clock [get_clocks $Group]
    Emit ${Group}_INTERNAL_SETUP_WNS_NS [PathSlack max -from $Clock -to $Clock]
    Emit ${Group}_INTERNAL_HOLD_WNS_NS [PathSlack min -from $Clock -to $Clock]
    report_timing -from $Clock -to $Clock -delay_type max -max_paths 10 -significant_digits 6 > [file join $Out ${Group}_internal_setup.rpt]
    report_timing -from $Clock -to $Clock -delay_type min -max_paths 10 -significant_digits 6 > [file join $Out ${Group}_internal_hold.rpt]
}
if {$Top eq "E203Tpu"} {
    set Sync [FindCells {(RequestSynchronizer|AcknowledgeSynchronizer)_reg\[[01]\]$}]
    if {[sizeof_collection $Sync] != 8} {error "Synchronizer structure changed during compile"}
    Emit CDC_SYNC_FLOPS [sizeof_collection $Sync]
    foreach {Channel Budget} [list RequestChannel 6.666667 ResponseChannel $CpuPeriod] {
        set From [RegisterPins [FindCells "${Channel}/SourcePayload_reg"] clock]
        set To [RegisterPins [FindCells "${Channel}/DestinationData_reg"] data]
        Emit ${Channel}_MAX_DELAY_BUDGET_NS $Budget
        Emit ${Channel}_MAX_DELAY_WNS_NS [PathSlack max -from $From -to $To]
        report_timing -from $From -to $To -delay_type max -max_paths 20 -significant_digits 6 > [file join $Out ${Channel}_max.rpt]
        report_timing -from $From -to $To -delay_type min -max_paths 20 -significant_digits 6 > [file join $Out ${Channel}_min.rpt]
    }
    Emit CDC_SIGNOFF "PENDING; delay-constrained handshake buses; physical skew/MTBF/CDC signoff not established"
}
Emit PHYSICAL_STATUS "NOT_RUN; no placement/CTS/extracted parasitics or worst-corner signoff"
Emit ASIC_REPORTS_COMPLETE $Out
close $Summary
