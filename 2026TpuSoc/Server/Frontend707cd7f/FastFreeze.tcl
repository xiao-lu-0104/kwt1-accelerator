# Preserve the original predicate, without repeatedly copying a growing collection.
proc FastFrozenCollection {} {
    set Started [clock seconds]
    puts "HOLD_STAGE: freeze_selection_start"
    set All [get_cells -hierarchical]
    set Expected 0
    foreach_in_collection Cell $All {
        set Name [get_object_name $Cell]
        if {![InSram $Name] && ![SramAncestor $Name]} {incr Expected}
    }
    set Frozen [filter_collection $All {full_name !~ Tpu/Core/Sram/* && full_name != Tpu && full_name != Tpu/Core && full_name != Tpu/Core/Sram}]
    if {[sizeof_collection $Frozen] != $Expected} {
        error "Bulk freeze selection count differs from original predicate"
    }
    foreach_in_collection Cell $Frozen {
        set Name [get_object_name $Cell]
        if {[InSram $Name] || [SramAncestor $Name]} {
            error "Bulk freeze selected an excluded SRAM object: $Name"
        }
    }
    puts "HOLD_STAGE: freeze_selection_complete count=$Expected elapsed_seconds=[expr {[clock seconds]-$Started}]"
    return $Frozen
}
