# Inspect saved mapped designs only. Never compile, optimize or edit a checkpoint.
if {[catch {
set Out $::env(TPU_ASIC_OUT)
set Tools $::env(TPU_SHARED_TOOLS)
set Mode $::env(TPU_REPORT_MODE)
set target_library [list $::env(TPU_STDCELL_DB)]
set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
file mkdir $Out
cd $Out
read_ddc $::env(TPU_REPORT_DDC)
current_design e203_subsys_nice_core
if {![link]} {error "Saved checkpoint link failed"}
source [file join $Tools AsicCommon.tcl]
source [file join $Tools HoldPolicy.tcl]
set Clock [get_clocks -quiet CoreClock]
if {[sizeof_collection [all_clocks]] != 1 || [sizeof_collection $Clock] != 1} {error "Expected one CoreClock"}
if {abs([get_attribute $Clock period] - 6.666667) > 0.000001} {error "Unexpected clock period"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Expected 56 mapped SRAM macros"}
set Lib [get_lib_cells -quiet */RAMSP1024X16]
if {[sizeof_collection $Lib] != 1} {error "Missing real SRAM library"}
set MacroArea [get_attribute $Lib area]
if {abs($MacroArea - 9148.524700) > 0.01} {error "Unexpected SRAM area"}
set Pins [get_pins -of_objects $Macros -filter {direction == in && full_name !~ */CLK}]
if {![sizeof_collection $Pins]} {error "Missing SRAM data/control inputs"}
set F [open metrics.tsv w]
foreach {Key Value} [list SETUP_WNS_NS [PathSlack max] HOLD_WNS_NS [PathSlack min] \
    SRAM_INPUT_HOLD_WNS_NS [PathSlack min -to $Pins] AREA [LibraryLeafArea] SRAM_AREA [expr {56*$MacroArea}]] {
    puts $F "$Key\t$Value"
}
close $F
write_sdc -nosplit snapshot.sdc
set F [open timing_signature.txt w]
foreach Line [TimingSignature snapshot.sdc] {puts $F $Line}
close $F
set Before [dict create]
if {$Mode eq "candidate"} {
    set F [open [file join $::env(TPU_REPORT_BASELINE) cells.tsv] r]
    while {[gets $F Line] >= 0} {
        set Fields [split $Line "\t"]
        dict set Before [lindex $Fields 0] [lindex $Fields 1]
    }
    close $F
}
set F [open cells.tsv w]
set Connections [open changed_connections.tsv w]
foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set Name [get_object_name $Cell]
    set Ref [get_attribute $Cell ref_name]
    puts $F "$Name\t$Ref"
    if {$Ref ni {**logic_0** **logic_1**} && [sizeof_collection [get_lib_cells -quiet */$Ref]] != 1} {
        error "Unmapped or ambiguous leaf: $Name $Ref"
    }
    if {$Mode eq "candidate" && ![InSram $Name] &&
        (![dict exists $Before $Name] || [dict get $Before $Name] ne $Ref)} {
        foreach_in_collection Pin [get_pins -of_objects $Cell] {
            set Nets [get_nets -quiet -of_objects $Pin]
            set Names {}
            if {[sizeof_collection $Nets]} {
                set Neighbors [get_pins -quiet -of_objects $Nets]
                foreach_in_collection Neighbor $Neighbors {lappend Names [get_object_name $Neighbor]}
            }
            puts $Connections "$Name\t$Ref\t[get_object_name $Pin]\t[get_attribute $Pin direction]\t[get_object_name $Nets]\t[join $Names ,]"
        }
    }
}
close $F
close $Connections
report_area -hierarchy > area.rpt
report_units > units.rpt
report_reference -hierarchy > references.rpt
report_qor > qor.rpt
check_design > check_design.rpt
check_timing > check_timing.rpt
report_constraint -all_violators > constraint_violations.rpt
report_timing -delay_type max -max_paths 20 -significant_digits 6 > setup.rpt
report_timing -delay_type min -max_paths 20 -significant_digits 6 > hold.rpt
report_timing -delay_type min -to $Pins -max_paths 10 -significant_digits 6 > sram_input_hold.rpt
puts "SHARED_SNAPSHOT_COMPLETE: $Mode $Out"
} Error]} {
    puts stderr "SHARED_SNAPSHOT_ERROR: $Error"
    exit 1
}
exit 0
