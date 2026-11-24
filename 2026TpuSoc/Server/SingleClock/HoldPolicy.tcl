# Hold recovery policy, factored out for selection/regression tests.
proc InSram {Name} {return [string match {Tpu/Core/Sram/*} $Name]}
proc SramAncestor {Name} {return [expr {$Name in {Tpu Tpu/Core Tpu/Core/Sram}}]}
proc TimingSignature {File} {
    set F [open $File r]
    set Text [read $F]
    close $F
    set Lines {}
    foreach Line [split $Text "\n"] {
        set Line [string trim $Line]
        if {$Line eq "" || [string match {#*} $Line]} {continue}
        # These are optimization permissions, not timing requirements.
        if {[regexp {^(set_fix_hold|set_dont_touch)\s} $Line]} {continue}
        lappend Lines $Line
    }
    return [lsort $Lines]
}
proc OutsideReferences {} {
    set Result [dict create]
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        set Name [get_object_name $Cell]
        if {![InSram $Name]} {dict set Result $Name [get_attribute $Cell ref_name]}
    }
    return $Result
}
proc AssertSameReferences {Before After} {
    if {[dict size $Before] != [dict size $After]} {error "Outside-SRAM leaf count changed"}
    dict for {Name Ref} $Before {
        if {![dict exists $After $Name] || [dict get $After $Name] ne $Ref} {
            error "Outside-SRAM mapped cell changed: $Name"
        }
    }
}
