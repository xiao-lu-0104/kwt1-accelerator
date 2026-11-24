# Physical identity is independent of the cell bbox, which includes a hard keepout.
proc PgPoint {Values} {
    if {[llength $Values]!=2} {error "Unexpected physical origin"}
    set R {}
    foreach V $Values {lappend R [format %.9f $V]}
    return $R
}
proc PgMacroSignature {} {
    set D [dict create]
    foreach_in_collection C [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}] {
        set Pins {}
        foreach_in_collection P [get_pins -physical_context -of_objects $C] {
            set Name [lindex [split [get_object_name $P] /] end]
            if {$Name ni {VDDCE VDDPE VSSE}} {continue}
            set B {}
            foreach V [IoBox $P] {lappend B [format %.9f $V]}
            lappend Pins [list $Name $B]
        }
        if {[llength $Pins]!=3} {error "Incomplete macro PG identity: [get_object_name $C]"}
        dict set D [get_object_name $C] [list [get_attribute $C ref_name] \
            [PgPoint [get_attribute $C origin]] [get_attribute $C orientation] [lsort $Pins]]
    }
    return $D
}
proc PgReadSignature {File} {
    set F [open $File r];set Header [gets $F]
    if {$Header ne "instance\tvalue"} {close $F;error "Unexpected baseline signature header"}
    set D [dict create]
    while {[gets $F Line]>=0} {
        set Fields [split $Line "\t"]
        if {[llength $Fields]!=2 || [dict exists $D [lindex $Fields 0]]} {close $F;error "Invalid baseline signature row"}
        dict set D [lindex $Fields 0] [lindex $Fields 1]
    }
    close $F
    return $D
}
proc PgWriteSignature {File Data} {
    set F [open $File w];puts $F "instance\tvalue"
    dict for {N V} $Data {puts $F "$N\t$V"}
    close $F
}
proc PgReadBoxes {File} {
    set F [open $File r]
    if {[gets $F] ne "instance\tx1\ty1\tx2\ty2"} {close $F;error "Unexpected physical bbox header"}
    set D [dict create]
    while {[gets $F Line]>=0} {
        set Fields [split $Line "\t"]
        if {[llength $Fields]!=5 || [dict exists $D [lindex $Fields 0]]} {close $F;error "Invalid original physical bbox"}
        dict set D [lindex $Fields 0] [lrange $Fields 1 end]
    }
    close $F
    if {[dict size $D]!=120} {error "Expected120 original macro bboxes"}
    return $D
}
proc PgRequireFixed {Macros} {
    foreach_in_collection C $Macros {
        if {![get_attribute $C is_fixed]} {error "Macro is no longer fixed: [get_object_name $C]"}
    }
}
proc PgCheckSourceIo {File} {
    set F [open $File r]
    if {[gets $F] ne "port\tterminal\tx1\ty1\tx2\ty2\tlayers"} {close $F;error "Unexpected source IO header"}
    set Expected [dict create]
    while {[gets $F Line]>=0} {
        set Fields [split $Line "\t"]
        if {[llength $Fields]!=7 || [dict exists $Expected [lindex $Fields 0]]} {close $F;error "Invalid source IO row"}
        dict set Expected [lindex $Fields 0] [lrange $Fields 2 end]
    }
    close $F
    set Ports [get_ports -quiet *]
    if {[sizeof_collection $Ports]!=[dict size $Expected]} {error "Recovered IO port count changed"}
    foreach_in_collection P $Ports {
        set N [get_object_name $P]
        if {![dict exists $Expected $N]} {error "Unexpected recovered signal port: $N"}
        set T [get_terminals -of_objects $P]
        if {[sizeof_collection $T]!=1} {error "Recovered signal terminal count changed: $N"}
        set Values [dict get $Expected $N];set Actual [IoBox $T]
        for {set I 0} {$I<4} {incr I} {
            if {abs([lindex $Actual $I]-[lindex $Values $I])>0.000001} {error "RECOVERED_IO_CHANGED_BEFORE_PG: $N expected=$Values actual=$Actual"}
        }
        if {[IoLayers $T] ne [lindex $Values 4]} {error "Recovered IO layer changed: $N"}
    }
}
