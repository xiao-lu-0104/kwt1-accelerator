# Actual PG construction on copied current-707cd7f checkpoints only.
source [file join [file dirname [info script]] PrCommon.tcl]
source [file join [file dirname [info script]] IoGeometry.tcl]
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

proc PgLeafSignature {} {
    set D [dict create]
    foreach_in_collection C [get_cells -hierarchical -filter {is_hierarchical == false}] {
        dict set D [get_object_name $C] [get_attribute $C ref_name]
    }
    return $D
}
proc PgSame {Before After Kind} {
    if {[dict size $Before]!=[dict size $After]} {error "$Kind count changed"}
    dict for {N V} $Before {
        if {![dict exists $After $N] || [dict get $After $N] ne $V} {
            PrRecord IDENTITY_DIFF_BEFORE "$Kind $N $V"
            if {[dict exists $After $N]} {PrRecord IDENTITY_DIFF_AFTER "$Kind $N [dict get $After $N]"}
            error "$Kind changed: $N"
        }
    }
}
proc PgSave {Tag} {
    PrStep save_block [list save_block]
    PrStep save_library [list save_lib]
    PrStep checkpoint_def [list write_def "${Tag}.def"]
    PrRecord CHECKPOINT_SAVED $Tag
    flush stdout
}
proc PgConnect {} {
    foreach {Net Names} {VDD {VDD VDDCE VDDPE} VSS {VSS VSSE}} {
        foreach Name $Names {
            set P [get_pins -quiet -physical_context "*/$Name"]
            if {[sizeof_collection $P]>0} {PrStep logical_pg_binding [list connect_pg_net -net $Net $P]}
        }
    }
}
proc PgExportIo {} {
    set F [open PortTerminalGeometry.tsv w]
    puts $F "port\tterminal\tx1\ty1\tx2\ty2\tlayers"
    foreach_in_collection P [get_ports -quiet *] {
        set T [get_terminals -of_objects $P]
        if {[sizeof_collection $T]!=1} {error "PG stage changed signal terminal cardinality: [get_object_name $P]"}
        puts $F "[get_object_name $P]\t[get_object_name $T]\t[join [IoBox $T] \t]\t[IoLayers $T]"
    }
    close $F
}
if {[catch {
    source PgConfig.tcl
    foreach {N O} {
        open_lib {} set_ref_libs {-ref_libs} open_block {} link_block {}
        set_host_options {-max_cores} set_fixed_objects {} save_block {} save_lib {} write_def {}
    } {PrNeed $N $O}
    PrStep open_current_copy [list open_lib $DesignLib]
    PrStep copied_references [list set_ref_libs -ref_libs $RefLibs]
    PrStep current_block [list open_block e203_cpu_top]
    PrStep link [list link_block] 1
    PrStep cores [list set_host_options -max_cores 4]
    if {[sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]!=0} {error "Unbound cells in copied design"}
    foreach {Ref Expected} {RAMSP1024X16 56 RAMSP4096X16 64} {
        if {[sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]!=$Expected} {error "Current macro class changed"}
    }
    PrStep scenario [list current_scenario FUNC_INITIAL]
    set Clk [get_clocks -quiet CoreClock]
    if {[sizeof_collection $Clk]!=1 || abs([get_attribute $Clk period]-$ExpectedPeriod)>1e-9} {error "Current clock budget changed"}
    set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}]
    set BeforeMacros [PgMacroSignature]
    set BeforeLeaves [PgLeafSignature]
    if {$Phase eq "pg_core"} {
        PgSame [PgReadSignature $BaselineLeaves] $BeforeLeaves SOURCE_LOGICAL_MAP
        PgSame [PgReadSignature $BaselineMacros] $BeforeMacros SOURCE_MACRO_PHYSICAL_IDENTITY
        set SourcePhysicalBoxes [PgReadBoxes $BaselineBoxes]
        PgCheckSourceIo $BaselineIo
        PrRecord RECOVERY_BASELINE_MATCH LOGICAL_LEAVES_AND_MACRO_PHYSICAL_IDENTITY
    }
    PrStep fix_macros [list set_fixed_objects $Macros]
    PgRequireFixed $Macros
    switch $Phase {
        pg_core {
            foreach {N O} {
                create_pg_ring_pattern {-horizontal_layer -vertical_layer -horizontal_width -vertical_width -horizontal_spacing -vertical_spacing}
                create_pg_mesh_pattern {-layers} create_pg_std_cell_conn_pattern {-layers}
                create_pg_macro_conn_pattern {-pin_conn_type -direction -layers -pin_layers -width -spacing -pitch -via_rule}
                set_pg_strategy {-core -macros -pattern -extension -blockage}
                set_pg_via_master_rule {-via_array_dimension}
                set_pg_strategy_via_rule {-via_rule} compile_pg {-strategies -via_rule}
            } {PrNeed $N $O}
            foreach L {M1 M2 M3 M4 M5 M6 M7 TM2} {
                if {[sizeof_collection [get_layers -quiet $L]]!=1} {error "Actual stack layer absent: $L"}
            }
            # Continue only the saved rails library; existing ring/mesh/rails stay intact.
            PgConnect
            # The installed manual permits omitted contact_code; request a 1x1 default contact.
            # Non-symmetric contact codes may ignore the array option: native checks remain mandatory.
            PrStep macro_pin_via [list set_pg_via_master_rule PIN707_1X1 -via_array_dimension {1 1}]
            PrStep macro_pattern [list create_pg_macro_conn_pattern MACRO707_M5 -pin_conn_type long_pin \
                -direction horizontal -layers M5 -pin_layers {M4} -width 0.28 -spacing interleaving -pitch 42 \
                -via_rule {{intersection: adjacent} {via_master: PIN707_1X1}}]
            PrStep macro_strategy [list set_pg_strategy S_MACRO707 -macros $Macros -pattern {{name: MACRO707_M5} {nets: {VDD VSS}}}]
            PrStep macro_mesh_vias [list set_pg_strategy_via_rule V_MACRO707 -via_rule {
                {{{existing: strap} {layers: M6}} {strategies: S_MACRO707} {via_master: default}}
                {{intersection: undefined} {via_master: NIL}}
            }]
            PrStep macro_compile [list compile_pg -strategies S_MACRO707 -via_rule V_MACRO707]
            PgConnect
            PgSave pg_complete
        }
        default {error "Unknown PG phase: $Phase"}
    }
    PgSame $BeforeMacros [PgMacroSignature] MACRO_PHYSICAL_IDENTITY
    PgSame $BeforeLeaves [PgLeafSignature] LOGICAL_LEAVES
    PgRequireFixed $Macros
    PgExportIo
    PrRecord MACRO_AND_LEAF_SIGNATURE UNCHANGED
    PrRecord RESULT "NEW_707CD7F_PG_PHASE_COMPLETE $Phase"
} Why]} {
    PrRecord ERROR $Why
    puts stderr $::errorInfo
    PrRecord RESULT NEW_707CD7F_PG_PHASE_INCOMPLETE_RETAIN_CHECKPOINTS
    exit 2
}
exit 0
