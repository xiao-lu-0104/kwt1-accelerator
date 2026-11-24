# Read one existing checkpoint in a fresh DC session. No optimization or writes to source run.
if {[catch {
    set Out $::env(TPU_REVIEW_OUT)
    cd $Out
    set_svf -off
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
    set Loaded [read_ddc $::env(TPU_REVIEW_DDC)]
    if {[sizeof_collection [get_designs -quiet e203_subsys_nice_core]] != 1} {error "Missing checkpoint top"}
    current_design e203_subsys_nice_core
    if {![link]} {error "Checkpoint link failed"}
    source [file join $::env(TPU_ORIGINAL_TOOLS) AsicCommon.tcl]
    set F [open leaves.tsv w]
    puts $F "name\tref\tregion"
    set Count 0
    set MacroCount 0
    set Unmapped 0
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        set Name [get_object_name $Cell]
        set Ref [get_attribute $Cell ref_name]
        set Region outside
        if {[string match {Tpu/Core/Sram/*} $Name]} {set Region sram}
        puts $F "$Name\t$Ref\t$Region"
        incr Count
        if {$Ref eq "RAMSP1024X16"} {incr MacroCount}
        if {$Ref ni {**logic_0** **logic_1**} && [sizeof_collection [get_lib_cells -quiet */$Ref]] != 1} {incr Unmapped}
    }
    close $F
    report_area -hierarchy > area.rpt
    report_units > units.rpt
    report_reference -hierarchy > references.rpt
    report_qor > qor.rpt
    report_clock > clocks.rpt
    check_design > check_design.rpt
    check_timing > check_timing.rpt
    report_constraint -all_violators > constraint_violations.rpt
    report_timing -delay_type max -max_paths 20 -significant_digits 9 > setup.rpt
    report_timing -delay_type min -max_paths 20 -significant_digits 9 > hold.rpt
    set F [open summary.txt w]
    foreach {Key Value} [list TOP e203_subsys_nice_core LEAVES $Count SRAM_COUNT $MacroCount \
        UNMAPPED_OR_AMBIGUOUS_LEAVES $Unmapped AREA_UM2 [LibraryLeafArea] \
        SETUP_WNS_NS [PathSlack max] HOLD_WNS_NS [PathSlack min] \
        PURPOSE "checkpoint diagnosis only; original outside-SRAM policy failure remains"] {
        puts $F "$Key: $Value"
    }
    close $F
    puts "CHECKPOINT_REVIEW_COMPLETE: $Out"
} Why]} {
    puts stderr "CHECKPOINT_REVIEW_ERROR: $Why"
    puts stderr $::errorInfo
    exit 1
}
exit 0
