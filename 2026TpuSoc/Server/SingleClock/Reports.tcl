set Clocks [get_clocks *]
if {[sizeof_collection $Clocks] != 1 || [get_object_name $Clocks] ne "CoreClock"} {
    error "Expected exactly one clock, CoreClock"
}
if {abs([get_attribute $Clocks period] - 6.666667) > 0.000001} {
    error "Unexpected common clock period"
}
report_area -hierarchy > [file join $Out area.rpt]
report_qor > [file join $Out qor.rpt]
report_units > [file join $Out units.rpt]
report_clock > [file join $Out clocks.rpt]
report_reference -hierarchy > [file join $Out references.rpt]
check_design > [file join $Out check_design.rpt]
check_timing > [file join $Out check_timing.rpt]
report_constraint -all_violators > [file join $Out constraint_violations.rpt]
report_timing -delay_type max -max_paths 20 -significant_digits 6 > [file join $Out setup.rpt]
report_timing -delay_type min -max_paths 20 -significant_digits 6 > [file join $Out hold.rpt]
report_timing -from [get_clocks CoreClock] -to [get_clocks CoreClock] -delay_type max -max_paths 10 -significant_digits 6 > [file join $Out internal_setup.rpt]
report_timing -from [get_clocks CoreClock] -to [get_clocks CoreClock] -delay_type min -max_paths 10 -significant_digits 6 > [file join $Out internal_hold.rpt]
set Summary [open [file join $Out summary.txt] w]
proc Emit {Key Value} {
    global Summary
    puts "$Key: $Value"
    puts $Summary "$Key: $Value"
}
set Setup [PathSlack max]
set Hold [PathSlack min]
Emit TOP $Top
Emit SOURCE_COMMIT 88e529eff28f4ba75fc250fe2e03310e267b3af7
Emit CLOCK_PROFILE "one CoreClock, 6.666667ns, CPU/TPU/NICE/AXI synchronous"
Emit CORNER "SMIC40 + actual RAMSP1024X16; TT 1.1V 25C; pre-layout"
Emit CONSTRAINT_STATUS "engineering assumptions; setup/hold uncertainty=0.2/0.1ns; not official/signoff"
Emit SRAM_CELLS "56 x RAMSP1024X16; 112KiB"
Emit SRAM_LIBRARY_AREA [expr {56*$MacroArea}]
Emit TOTAL_LIBRARY_CELL_AREA [LibraryLeafArea]
Emit AREA_METHOD "sum of mapped leaf library-cell areas, including SRAM"
Emit SETUP_WNS_NS $Setup
Emit HOLD_WNS_NS $Hold
Emit SETUP_STATUS [expr {$Setup >= 0 ? "PASS" : "FAIL"}]
Emit HOLD_STATUS [expr {$Hold >= 0 ? "PASS" : "FAIL"}]
Emit INTERNAL_SETUP_WNS_NS [PathSlack max -from [get_clocks CoreClock] -to [get_clocks CoreClock]]
Emit INTERNAL_HOLD_WNS_NS [PathSlack min -from [get_clocks CoreClock] -to [get_clocks CoreClock]]
if {$Top eq "E203TpuBackend"} {
    # Bucket by register capture hierarchy. CPU->TPU and TPU->CPU paths remain
    # ordinary single-cycle paths; none are cut or granted CDC max/min delays.
    set DataPins [all_registers -data_pins]
    foreach Block {Cpu Tpu Bus} {
        set Pins ""
        foreach_in_collection Pin $DataPins {
            if {[string match "${Block}/*" [get_object_name $Pin]]} {set Pins [add_to_collection $Pins $Pin]}
        }
        if {![sizeof_collection $Pins]} {Emit ${Block}_CAPTURE_STATUS "no data pins selected"; continue}
        Emit ${Block}_CAPTURE_SETUP_WNS_NS [PathSlack max -to $Pins]
        Emit ${Block}_CAPTURE_HOLD_WNS_NS [PathSlack min -to $Pins]
        report_timing -to $Pins -delay_type max -max_paths 10 -significant_digits 6 > [file join $Out ${Block}_capture_setup.rpt]
        report_timing -to $Pins -delay_type min -max_paths 10 -significant_digits 6 > [file join $Out ${Block}_capture_hold.rpt]
    }
}
Emit PHYSICAL_STATUS "NOT_RUN; TCM/DDR PHY outside boundary; no CTS/extracted parasitics/multi-corner signoff"
Emit ASIC_REPORTS_COMPLETE $Out
close $Summary
