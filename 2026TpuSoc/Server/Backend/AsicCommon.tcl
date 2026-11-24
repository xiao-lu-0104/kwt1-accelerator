# Shared DC utilities. Timing paths are collections, not scalar values.
proc NumericMinimum {Values} {
    if {![llength $Values]} {error "No numeric timing values"}
    set Worst ""
    foreach Value $Values {
        if {![string is double -strict $Value] || [regexp -nocase {nan|inf} $Value]} {
            error "Invalid/non-finite timing value: $Value"
        }
        if {$Worst eq "" || $Value < $Worst} {set Worst $Value}
    }
    return $Worst
}
proc PathSlack {Kind args} {
    set Paths [eval get_timing_paths -delay_type $Kind -max_paths 1 $args]
    if {![sizeof_collection $Paths]} {error "No $Kind constrained timing path: $args"}
    set Values {}
    foreach_in_collection Path $Paths {lappend Values [get_attribute $Path slack]}
    return [NumericMinimum $Values]
}
proc FindCells {Pattern} {
    set Result ""
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        if {[regexp $Pattern [get_object_name $Cell]]} {set Result [add_to_collection $Result $Cell]}
    }
    return $Result
}
proc RegisterPins {Cells Kind} {
    if {$Kind eq "clock"} {
        set Pattern {/(CK|CLK|CP|C)$}
    } elseif {$Kind eq "data"} {
        set Pattern {/D$}
    } else {error "Unknown register pin kind: $Kind"}
    set Result ""
    foreach_in_collection Cell $Cells {
        set Matches ""
        foreach_in_collection Pin [get_pins -of_objects $Cell] {
            if {[regexp $Pattern [get_object_name $Pin]]} {set Matches [add_to_collection $Matches $Pin]}
        }
        if {[sizeof_collection $Matches] != 1} {
            error "Expected one $Kind pin on [get_object_name $Cell]"
        }
        set Result [add_to_collection $Result $Matches]
    }
    if {![sizeof_collection $Result]} {error "No $Kind register pins selected"}
    return $Result
}
proc LibraryLeafArea {} {
    set Total 0.0
    array set Cache {}
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        set Ref [get_attribute $Cell ref_name]
        if {$Ref in {**logic_0** **logic_1**}} {continue}
        if {![info exists Cache($Ref)]} {
            set LibCell [get_lib_cells -quiet */$Ref]
            if {[sizeof_collection $LibCell] != 1} {error "Unmapped or ambiguous reference: $Ref"}
            set Value [get_attribute $LibCell area]
            if {![string is double -strict $Value] || $Value < 0} {error "Invalid library area for $Ref"}
            set Cache($Ref) $Value
        }
        set Total [expr {$Total + $Cache($Ref)}]
    }
    if {$Total <= 0} {error "No positive mapped-cell area"}
    return $Total
}
proc FrozenBudgetSignature {File} {
    set F [open $File r]
    set Text [read $F]
    close $F
    set Result {}
    foreach Line [split $Text "\n"] {
        set Line [string trim $Line]
        if {[regexp {^(create_clock|create_generated_clock|set_clock_uncertainty|set_clock_transition|set_clock_latency|set_input_delay|set_output_delay|set_input_transition|set_load)\s} $Line]} {
            lappend Result $Line
        }
    }
    return [lsort $Result]
}
