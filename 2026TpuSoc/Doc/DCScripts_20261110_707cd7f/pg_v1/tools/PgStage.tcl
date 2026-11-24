# Actual PG construction on copied current-707cd7f checkpoints only.
source [file join [file dirname [info script]] PrCommon.tcl]
source [file join [file dirname [info script]] IoGeometry.tcl]
proc PgMacroSignature {} {
    set D [dict create]
    foreach_in_collection C [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}] {
        dict set D [get_object_name $C] [list [get_attribute $C ref_name] [get_attribute $C bbox]]
    }
    return $D
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
        if {![dict exists $After $N] || [dict get $After $N] ne $V} {error "$Kind changed: $N"}
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
    PrStep fix_macros [list set_fixed_objects $Macros]
    switch $Phase {
        legalize {
            foreach {N O} {create_keepout_margin {-type -outer} legalize_placement {} check_legality {}} {PrNeed $N $O}
            # Keep standard cells away from the same lower-layer PG halo.
            PrStep macro_keepout [list create_keepout_margin -type hard -outer {1.12 1.12 1.12 1.12} $Macros]
            PrStep legalize_cells [list legalize_placement]
            PgSame $BeforeMacros [PgMacroSignature] MACRO_REF_BBOX
            PgSame $BeforeLeaves [PgLeafSignature] LOGICAL_LEAVES
            PgSave legalized
            redirect legality.rpt {check_legality}
        }
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
            PgConnect
            PrStep ring_pattern [list create_pg_ring_pattern R707 -horizontal_layer M7 -vertical_layer TM2 \
                -horizontal_width 2.24 -vertical_width 2.52 -horizontal_spacing 1.68 -vertical_spacing 1.68]
            PrStep ring_strategy [list set_pg_strategy S_RING707 -core -pattern {{name: R707} {nets: {VDD VSS}} {offset: {5.04 5.04}}}]
            PrStep ring_compile [list compile_pg -strategies S_RING707]
            PgSave ring
            # M4 macro pins are ~0.11um. Do not lay wide global M4 straps across them.
            # Also exclude global M5 over macros, reserving M5 there for local macro straps.
            set LowerBlockages {}
            set Core [concat {*}[get_attribute [current_block] core_area_bbox]]
            foreach_in_collection C $Macros {
                lassign [IoBox $C] X1 Y1 X2 Y2
                set X1 [expr {max([lindex $Core 0],$X1-1.12)}];set Y1 [expr {max([lindex $Core 1],$Y1-1.12)}]
                set X2 [expr {min([lindex $Core 2],$X2+1.12)}];set Y2 [expr {min([lindex $Core 3],$Y2+1.12)}]
                set Poly [list [list $X1 $Y1] [list $X2 $Y1] [list $X2 $Y2] [list $X1 $Y2]]
                lappend LowerBlockages [list {layers: M1 M2 M3 M4 M5} [list polygon: $Poly]]
            }
            PrStep mesh_pattern [list create_pg_mesh_pattern MESH707_42 -layers {
                {{vertical_layer: M2} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
                {{horizontal_layer: M3} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
                {{vertical_layer: M4} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
                {{horizontal_layer: M5} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
                {{vertical_layer: M6} {width: 0.56} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
                {{horizontal_layer: M7} {width: 1.12} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
                {{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
            }]
            PrStep mesh_strategy [list set_pg_strategy S_MESH707 -core -pattern {{name: MESH707_42} {nets: {VDD VSS}}} \
                -extension {{stop: outermost_ring}} -blockage $LowerBlockages]
            PrStep mesh_compile [list compile_pg -strategies S_MESH707]
            PgSave mesh42
            PrStep rail_pattern [list create_pg_std_cell_conn_pattern RAIL707 -layers {M1}]
            PrStep rail_strategy [list set_pg_strategy S_RAIL707 -core -pattern {{name: RAIL707} {nets: {VDD VSS}}} -blockage $LowerBlockages]
            PrStep rail_vias [list set_pg_strategy_via_rule V_RAIL707 -via_rule {
                {{{existing: strap} {layers: M2}} {strategies: S_RAIL707} {via_master: default}}
                {{intersection: undefined} {via_master: NIL}}
            }]
            PrStep rail_compile [list compile_pg -strategies S_RAIL707 -via_rule V_RAIL707]
            PgSave rails
            # The installed manual permits omitted contact_code; request a 1x1 default contact.
            # Non-symmetric contact codes may ignore the array option: native checks remain mandatory.
            PrStep macro_pin_via [list set_pg_via_master_rule PIN707_1X1 -via_array_dimension {1 1}]
            PrStep macro_pattern [list create_pg_macro_conn_pattern MACRO707_M5 -pin_conn_type long_pin \
                -direction horizontal -layers M5 -pin_layers {M4} -width 0.28 -spacing interleaving -pitch 42 \
                -via_rule {{{layers: M4} {layers: M5} {via_master: PIN707_1X1}}}]
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
    PgSame $BeforeMacros [PgMacroSignature] MACRO_REF_BBOX
    PgSame $BeforeLeaves [PgLeafSignature] LOGICAL_LEAVES
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
