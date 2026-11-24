source [file join [file dirname [info script]] PrCommon.tcl]
proc CoarseSignature {} {
    set result [dict create]
    foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        dict set result [get_object_name $cell] [get_attribute $cell ref_name]
    }
    return $result
}
if {[catch {
    source PrCoarseConfig.tcl
    PrRecord SCOPE ACCELERATOR_56_PRIVATE_SRAM_MACROS
    PrRecord LIMITATIONS COARSE_ONLY_NO_RC_PG_ROUTING_CTS_OR_SIGNOFF
    foreach {name options} {
        open_lib {} set_ref_libs {-ref_libs} open_block {} link_block {}
        set_host_options {-max_cores} create_placement {-floorplan -effort}
        report_placement {-hard_macro_overlap} get_attribute {} current_block {}
        get_cells {-hierarchical -filter} save_block {} save_lib {} write_def {}
    } {PrNeed $name $options}
    PrStep open_lib [list open_lib $PrDesignLib]
    PrStep set_ref_libs [list set_ref_libs -ref_libs $PrRefLibs]
    PrStep open_block [list open_block $PrTop]
    PrStep link_block [list link_block] 1
    set before [CoarseSignature]
    if {[dict size $before] != $PrExpectedLeaves} {error "Source leaf count changed"}
    set unbound [sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]
    if {$unbound != 0} {error "Unbound instances in copied library"}
    PrRecord UNBOUND_CELLS $unbound
    PrStep host_options [list set_host_options -max_cores 4]
    # Geometric initial placement, without a timing-driven or optimization claim.
    PrStep initial_coarse_placement [list create_placement -floorplan -effort low]
    set after [CoarseSignature]
    if {[dict size $before] != [dict size $after]} {error "Coarse placement changed leaf count"}
    dict for {name ref} $before {
        if {![dict exists $after $name] || [dict get $after $name] ne $ref} {
            error "Coarse placement changed logical instance: $name"
        }
    }
    PrRecord LOGICAL_LEAF_SIGNATURE UNCHANGED
    PrRecord LEAF_CELLS [dict size $after]
    set macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
    if {[sizeof_collection $macros] != 56} {error "Expected 56 private SRAM macros"}
    set f [open core_bbox.txt w]
    puts $f [get_attribute [current_block] core_area_bbox]
    close $f
    set f [open macros.tsv w]
    puts $f "instance\tx1\ty1\tx2\ty2"
    foreach_in_collection cell $macros {
        set box [get_attribute $cell bbox]
        if {[llength $box] != 2 || [llength [lindex $box 0]] != 2 || [llength [lindex $box 1]] != 2} {
            error "Unexpected macro bbox: [get_object_name $cell] $box"
        }
        puts $f "[get_object_name $cell]\t[join [concat [lindex $box 0] [lindex $box 1]] \t]"
    }
    close $f
    redirect report_placement.rpt {report_placement -hard_macro_overlap}
    PrStep save_block [list save_block]
    PrStep save_lib [list save_lib]
    PrStep write_def [list write_def $PrDef]
    if {![file isfile $PrDef] || [file size $PrDef] == 0} {error "Coarse DEF missing"}
    PrReport report_design
    PrReport report_units
    PrRecord PRIVATE_MACROS 56
    PrRecord RESULT COARSE_PLACEMENT_NATIVE_COMPLETE_REVIEW_PENDING
} why]} {
    PrRecord ERROR $why
    puts stderr $::errorInfo
    PrReport report_placement -hard_macro_overlap
    PrRecord RESULT COARSE_PLACEMENT_FAILED_OR_INCOMPLETE
    exit 2
}
exit 0
