# Current 1109 system, one checkpointed implementation phase per process.
source [file join [file dirname [info script]] PrCommon.tcl]
proc Check {File Command} {
    puts "FULL_PR_CHECK_BEGIN: $File";flush stdout
    set Code [catch {redirect $File $Command} Why]
    PrRecord CHECK_EXECUTION "$File code=$Code result=$Why"
    if {$Code} {
        set F [open $File a];puts $F "CHECK_EXECUTION_ERROR: $Why";close $F
    }
    puts "FULL_PR_CHECK_END: $File";flush stdout
}
proc MacroSignature {} {
    set R [dict create]
    foreach_in_collection C [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}] {
        dict set R [get_object_name $C] [list [get_attribute $C ref_name] [get_attribute $C bbox]]
    }
    return $R
}
proc ConnectPower {} {
    foreach {Net Names} {VDD {VDD VDDCE VDDPE} VSS {VSS VSSE}} {
        foreach Name $Names {
            set P [get_pins -quiet -physical_context "*/$Name"]
            if {[sizeof_collection $P]>0} {PrStep connect_pg [list connect_pg_net -net $Net $P]}
        }
    }
}
if {[catch {
    source FullConfig.tcl
    PrRecord PHASE $Phase
    foreach {Name Options} {
        open_lib {} set_ref_libs {-ref_libs} open_block {} link_block {}
        set_host_options {-max_cores} set_fixed_objects {} save_block {} save_lib {} write_def {}
    } {PrNeed $Name $Options}
    PrStep open_checkpoint [list open_lib $DesignLib]
    PrStep current_references [list set_ref_libs -ref_libs $RefLibs]
    PrStep current_block [list open_block e203_cpu_top]
    PrStep link_checkpoint [list link_block] 1
    if {[sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]!=0} {error "Unresolved current system instances"}
    foreach {Ref Count} {RAMSP1024X16 56 RAMSP4096X16 64} {
        if {[sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]!=$Count} {error "SRAM count changed"}
    }
    set Before [MacroSignature]
    set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}]
    PrStep fix_current_macros [list set_fixed_objects $Macros]
    PrStep cores [list set_host_options -max_cores 4]
    PrStep scenario [list current_scenario FUNC_INITIAL]
    if {[sizeof_collection [get_clocks -quiet CoreClock]]!=1 || abs([get_attribute [get_clocks CoreClock] period]-6.66667)>0.000000001} {
        error "Current serialized 1109 core period changed"
    }
    switch $Phase {
        01_rc {
            foreach {N O} {
                read_parasitic_tech {-tlup -layermap -name -sanity_check}
                set_parasitic_parameters {-corners -early_spec -late_spec -early_temperature -late_temperature}
                set_ignored_layers {-min_routing_layer -max_routing_layer}
                set_block_pin_constraints {-self -allowed_layers} place_pins {-self}
            } {PrNeed $N $O}
            foreach L {M1 M2 M3 M4 M5 M6 M7 TM2} {
                if {[sizeof_collection [get_layers -quiet $L]]!=1} {error "Missing native stack layer $L"}
            }
            PrStep read_typ_rc [list read_parasitic_tech -tlup $RcTlu -layermap $RcMap -name TYP1109 -sanity_check advanced]
            PrStep bind_typ_rc [list set_parasitic_parameters -corners [get_corners INITIAL] \
                -early_spec TYP1109 -late_spec TYP1109 -early_temperature 25 -late_temperature 25]
            Check parasitic_parameters.rpt [list report_parasitic_parameters]
            set F [open parasitic_parameters.rpt r];set R [read $F];close $F
            if {[string first TYP1109 $R]<0} {error "Native parasitic report did not confirm the selected model"}
            PrStep signal_layers [list set_ignored_layers -min_routing_layer M2 -max_routing_layer TM2]
            PrStep pin_layers [list set_block_pin_constraints -self -allowed_layers {M3 M4 M5 M6}]
            PrStep assign_block_pins [list place_pins -self]
            PrRecord RC_CONDITION TT_TYP_25C_SAME_EARLY_LATE_NOT_MCMM_SIGNOFF
        }
        02_pg {
            foreach {N O} {
                create_pg_ring_pattern {-horizontal_layer -vertical_layer -horizontal_width -vertical_width -horizontal_spacing -vertical_spacing}
                create_pg_mesh_pattern {-layers} create_pg_std_cell_conn_pattern {-layers}
                create_pg_macro_conn_pattern {-pin_conn_type} set_pg_strategy {-core -pattern -extension}
                set_pg_strategy_via_rule {-via_rule} compile_pg {-strategies -via_rule}
                check_pg_connectivity {-check_macro_pins -check_std_cell_pins} check_pg_drc {}
            } {PrNeed $N $O}
            ConnectPower
            PrStep pg_ring_pattern [list create_pg_ring_pattern RING1109 -horizontal_layer M7 -vertical_layer TM2 \
                -horizontal_width {2.24} -vertical_width {2.52} -horizontal_spacing {1.68} -vertical_spacing {1.68}]
            PrStep pg_ring_strategy [list set_pg_strategy S_RING1109 -core \
                -pattern {{name: RING1109} {nets: {VDD VSS}} {offset: {5.04 5.04}}}]
            PrStep pg_ring_compile [list compile_pg -strategies S_RING1109]
            PrStep pg_mesh_pattern [list create_pg_mesh_pattern MESH1109 -layers {
                {{vertical_layer: M2} {width: 0.28} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{horizontal_layer: M3} {width: 0.28} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{vertical_layer: M4} {width: 0.28} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{horizontal_layer: M5} {width: 0.28} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{vertical_layer: M6} {width: 0.56} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{horizontal_layer: M7} {width: 1.12} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
            }]
            PrStep pg_mesh_strategy [list set_pg_strategy S_MESH1109 -core \
                -pattern {{name: MESH1109} {nets: {VDD VSS}}} -extension {{stop: outermost_ring}}]
            PrStep pg_mesh_compile [list compile_pg -strategies S_MESH1109]
            # Native default rail width follows the library PG pin geometry.
            PrStep pg_rail_pattern [list create_pg_std_cell_conn_pattern RAIL1109 -layers {M1}]
            PrStep pg_rail_strategy [list set_pg_strategy S_RAIL1109 -core -pattern {{name: RAIL1109} {nets: {VDD VSS}}}]
            PrStep pg_rail_vias [list set_pg_strategy_via_rule V_RAIL1109 -via_rule {
                {{{existing: strap} {layers: M2}} {strategies: S_RAIL1109} {via_master: default}}
                {{intersection: undefined} {via_master: NIL}}
            }]
            PrStep pg_rail_compile [list compile_pg -strategies S_RAIL1109 -via_rule V_RAIL1109]
            PrStep pg_macro_pattern [list create_pg_macro_conn_pattern MACRO1109 -pin_conn_type scattered_pin]
            PrStep pg_macro_strategy [list set_pg_strategy S_MACRO1109 -core -pattern {{name: MACRO1109} {nets: {VDD VSS}}}]
            PrStep pg_macro_vias [list set_pg_strategy_via_rule V_MACRO1109 -via_rule {
                {{{existing: strap}} {strategies: S_MACRO1109} {via_master: default}}
                {{intersection: undefined} {via_master: NIL}}
            }]
            PrStep pg_macro_compile [list compile_pg -strategies S_MACRO1109 -via_rule V_MACRO1109]
            ConnectPower
        }
        03_place {
            PrNeed place_opt {};PrNeed legalize_placement {}
            PrStep optimize_placement [list place_opt]
            PrStep legalize [list legalize_placement]
            ConnectPower
            Check legality.rpt [list check_legality]
        }
        04_cts {
            PrNeed clock_opt {};PrNeed set_propagated_clock {}
            PrStep clock_tree_and_opt [list clock_opt]
            PrStep propagated_clocks [list set_propagated_clock [all_clocks]]
            ConnectPower
            if {[llength [info commands report_clock_qor]]} {Check clock_qor.rpt [list report_clock_qor]}
        }
        05_route {
            PrNeed route_auto {}
            PrStep automatic_route [list route_auto]
            ConnectPower
            Check route_check.rpt [list check_routes]
        }
        06_route_opt {
            PrNeed route_opt {}
            PrStep optimize_routing [list route_opt]
            ConnectPower
            Check route_check.rpt [list check_routes]
        }
        07_export {
            ConnectPower
            PrNeed write_verilog {};PrNeed write_sdc {}
            PrStep final_verilog [list write_verilog routed.v]
            # Follow the installed output argument instead of assuming DC syntax.
            set F [open write_sdc_manual.txt r];set M [read $F];close $F
            if {[string first -output $M]>=0} {
                PrStep final_sdc [list write_sdc -output routed.sdc]
            } else {PrStep final_sdc [list write_sdc routed.sdc]}
            if {[llength [info commands write_parasitics]]} {
                PrNeed write_parasitics {-format -output}
                Check spef_export.log [list write_parasitics -format SPEF -output routed]
            }
            if {[llength [info commands write_sdf]]} {Check sdf_export.log [list write_sdf routed.sdf]}
            if {[llength [info commands write_gds]]} {
                Check gds_export.log [list write_gds routed_unmerged.gds]
                PrRecord GDS_SCOPE REFERENCE_VIEWS_UNMERGED_NOT_MANUFACTURING_SIGNOFF
            }
            Check route_check.rpt [list check_routes]
            Check legality.rpt [list check_legality]
        }
        default {error "Unknown implementation phase $Phase"}
    }
    set After [MacroSignature]
    if {[dict size $Before]!=[dict size $After]} {error "SRAM macro signature size changed"}
    dict for {Name Value} $Before {
        if {![dict exists $After $Name] || [dict get $After $Name] ne $Value} {error "Implementation moved or replaced a fixed SRAM macro: $Name"}
    }
    foreach {File Command} {
        qor.rpt {report_qor}
        setup.rpt {report_timing -delay_type max -max_paths 20}
        hold.rpt {report_timing -delay_type min -max_paths 20}
        constraints.rpt {report_constraints -all_violators}
        pg_connectivity.rpt {check_pg_connectivity -check_macro_pins all -check_std_cell_pins true}
        pg_drc.rpt {check_pg_drc}
    } {Check $File $Command}
    if {[llength [info commands report_clocks]]} {
        Check clocks.rpt [list report_clocks]
    } elseif {[llength [info commands report_clock_qor]]} {
        Check clocks.rpt [list report_clock_qor]
    } else {
        set F [open clocks.rpt w]
        foreach_in_collection C [all_clocks] {puts $F "[get_object_name $C] period=[get_attribute $C period]"}
        close $F
    }
    set F [open PhaseStatus.txt w]
    puts $F "PHASE: $Phase"
    puts $F "PRIVATE_MACROS: 56"
    puts $F "SHARED_MACROS: 64"
    puts $F "MACRO_SIGNATURE: UNCHANGED"
    puts $F "LEAVES: [sizeof_collection [get_cells -hierarchical -filter {is_hierarchical == false}]]"
    puts $F "CHECK_ACCEPTANCE: ACTUAL_REPORTS_RETAINED_NOT_SIGNOFF"
    close $F
    PrStep save_stage_block [list save_block]
    PrStep save_stage_lib [list save_lib]
    PrStep stage_def [list write_def checkpoint.def]
    puts "FULL_PR_PHASE_COMPLETE: $Phase"
} Why]} {
    PrRecord ERROR $Why
    puts stderr $::errorInfo
    puts "FULL_PR_PHASE_FAILED"
    exit 2
}
exit 0
