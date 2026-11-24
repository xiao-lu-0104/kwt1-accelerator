# 707cd7f only. Every action runs on a copied library with copied references.
source [file join [file dirname [info script]] PrCommon.tcl]
source [file join [file dirname [info script]] IoGeometry.tcl]
source [file join [file dirname [info script]] PgPhysical.tcl]

proc CpSame {Before After Kind} {
    if {[dict size $Before]!=[dict size $After]} {error "$Kind count changed"}
    dict for {N V} $Before {
        if {![dict exists $After $N] || [dict get $After $N] ne $V} {error "$Kind changed: $N"}
    }
}
proc CpLeaves {} {
    set D [dict create]
    foreach_in_collection C [get_cells -hierarchical -filter {is_hierarchical == false}] {
        dict set D [get_object_name $C] [get_attribute $C ref_name]
    }
    return $D
}
proc CpConnect {} {
    foreach {Net Names} {VDD {VDD VDDCE VDDPE} VSS {VSS VSSE}} {
        foreach Name $Names {
            set Pins [get_pins -quiet -physical_context "*/$Name"]
            if {[sizeof_collection $Pins]} {PrStep logical_pg_binding [list connect_pg_net -net $Net $Pins]}
        }
    }
}
proc CpReport {File Command} {
    puts "CONTINUE_CHECK_BEGIN: $File";flush stdout
    set Code [catch {redirect $File $Command} Why]
    PrRecord CHECK_EXECUTION "$File code=$Code result=$Why"
    if {$Code} {set F [open $File a];puts $F "CHECK_EXECUTION_ERROR: $Why";close $F}
    puts "CONTINUE_CHECK_END: $File";flush stdout
}
proc CpSave {} {
    global BaselineMacros BaselineIo Action
    # Macro identity and original grouped IO are acceptance gates, not waivers.
    CpSame [PgReadSignature $BaselineMacros] [PgMacroSignature] MACRO_PHYSICAL_IDENTITY
    PgCheckSourceIo $BaselineIo
    PrStep save_core_block [list save_block]
    PrStep save_core_lib [list save_lib]
    PrStep save_core_def [list write_def checkpoint.def]
    puts "CONTINUE_CORE_SAVED: $Action";flush stdout
}
proc CpTiming {} {
    CpReport setup.rpt [list report_timing -delay_type max -max_paths 20]
    CpReport hold.rpt [list report_timing -delay_type min -max_paths 20]
    CpReport qor.rpt [list report_qor]
    CpReport constraints.rpt [list report_constraints -all_violators]
}

proc PgConnect {} {CpConnect}
proc PgSave {Tag} {
    CpSave
    PrStep pg_subcheckpoint_$Tag [list write_def "${Tag}.def"]
}

if {[catch {
    source ContinueConfig.tcl
    PrStep library [list open_lib $DesignLib]
    PrStep refs [list set_ref_libs -ref_libs $RefLibs]
    PrStep block [list open_block e203_cpu_top]
    PrStep link [list link_block] 1
    PrStep cores [list set_host_options -max_cores 4]
    if {[sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]} {error "Unbound design"}
    foreach {Ref Expected} {RAMSP1024X16 56 RAMSP4096X16 64} {
        if {[sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]!=$Expected} {error "Current macro count changed"}
    }
    set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}]
    CpSame [PgReadSignature $BaselineMacros] [PgMacroSignature] SOURCE_MACRO_PHYSICAL_IDENTITY
    PgCheckSourceIo $BaselineIo
    PrStep fixed_macros [list set_fixed_objects $Macros]
    PgRequireFixed $Macros
    set Clock [get_clocks -quiet CoreClock]
    if {[sizeof_collection $Clock]!=1 || abs([get_attribute $Clock period]-$ExpectedPeriod)>1e-9} {error "Clock budget changed"}
    PrStep scenario [list current_scenario FUNC_INITIAL]
    switch $Action {
        01_rc {
            PrNeed read_parasitic_tech {-tlup -layermap -name -sanity_check}
            PrNeed set_parasitic_parameters {-corners -early_spec -late_spec -early_temperature -late_temperature}
            PrStep read_rc [list read_parasitic_tech -tlup $RcTlu -layermap $RcMap -name TYP707CONT -sanity_check advanced]
            PrStep bind_rc [list set_parasitic_parameters -corners [get_corners INITIAL] \
                -early_spec TYP707CONT -late_spec TYP707CONT -early_temperature 25 -late_temperature 25]
            PrStep route_layers [list set_ignored_layers -min_routing_layer M2 -max_routing_layer TM2]
            CpSame [PgReadSignature $BaselineLeaves] [CpLeaves] INITIAL_LOGICAL_LEAVES
            PrStep macro_keepout [list create_keepout_margin -type hard -outer {1.12 1.12 1.12 1.12} $Macros]
            set Option place.coarse.continue_on_missing_scandef
            PrStep no_scan_functional [list set_app_options -name $Option -value true]
            PrStep initial_legalize [list legalize_placement]
            CpSave
            CpReport rc.rpt [list report_parasitic_parameters]
            set F [open rc.rpt r];set Text [read $F];close $F
            if {[string first TYP707CONT $Text]<0} {error "Native RC binding not confirmed"}
        }
        02_pg_basic {
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
            PrStep mesh_pattern [list create_pg_mesh_pattern MESH707_84_BASIC -layers {
                {{vertical_layer: M2} {width: 0.28} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{vertical_layer: M6} {width: 0.56} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{horizontal_layer: M7} {width: 1.12} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 168} {offset: 10.08}}
            }]
            PrStep mesh_strategy [list set_pg_strategy S_MESH707 -core -pattern {{name: MESH707_84_BASIC} {nets: {VDD VSS}}} \
                -extension {{stop: outermost_ring}} -blockage $LowerBlockages]
            PrStep mesh_compile [list compile_pg -strategies S_MESH707]
            PgSave mesh84
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
                -direction horizontal -layers M5 -pin_layers {M4} -width 0.28 -spacing interleaving -pitch 84 \
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
        04_build_clock {
            CpReport clock_opt_manual.txt [list man clock_opt]
            set F [open clock_opt_manual.txt r];set Manual [read $F];close $F
            foreach Token {build_clock route_clock -from -to} {
                if {[string first $Token $Manual]<0} {error "Installed clock_opt manual lacks $Token"}
            }
            PrStep build_clock [list clock_opt -from build_clock -to build_clock]
            CpConnect;CpSave;CpTiming
        }
        04_route_clock {
            PrStep route_clock [list clock_opt -from route_clock -to route_clock]
            PrStep propagate [list set_propagated_clock [all_clocks]]
            CpConnect;CpSave;CpTiming
            if {[llength [info commands report_clock_qor]]} {CpReport clock_qor.rpt [list report_clock_qor]}
        }
        05_route {
            CpReport route_auto_manual.txt [list man route_auto]
            set F [open route_auto_manual.txt r];set Manual [read $F];close $F
            if {[string first -max_detail_route_iterations $Manual]>=0} {
                PrStep signal_route [list route_auto -max_detail_route_iterations 3]
            } else {
                puts "ROUTING_EFFORT: installed route_auto has no iteration option; using default"
                PrStep signal_route [list route_auto]
            }
            CpConnect;CpSave;CpTiming
        }
        07_export {
            CpConnect;CpSave
            PrStep verilog [list write_verilog routed.v]
            PrNeed write_sdc {}
            set F [open write_sdc_manual.txt r];set Text [read $F];close $F
            if {[string first -output $Text]>=0} {PrStep sdc [list write_sdc -output routed.sdc]} else {PrStep sdc [list write_sdc routed.sdc]}
            CpTiming
            CpReport route_check.rpt [list check_routes]
            CpReport legality.rpt [list check_legality]
            foreach Command {write_gds} {
                if {[llength [info commands $Command]]} {CpReport "${Command}_manual.txt" [list man $Command]}
            }
            if {[llength [info commands write_gds]]} {CpReport gds_export.log [list write_gds routed_unmerged.gds]}
        }
        connectivity {
            PrNeed check_pg_connectivity {-check_macro_pins -check_std_cell_pins}
            redirect connectivity.rpt {
                set Floating [check_pg_connectivity -check_macro_pins all -check_std_cell_pins all]
            }
            set F [open FloatingObjects.tsv w]
            puts $F "name\tobject_class\tref_name\tbbox\tnet_name"
            set Cells [open FloatingCells.tsv w]
            puts $Cells "name\tobject_class\tref_name\tbbox\tnet_name"
            foreach_in_collection O $Floating {
                set Values [list [get_object_name $O]];set Class UNAVAILABLE
                foreach A {object_class ref_name bbox net_name} {
                    if {[catch {get_attribute $O $A} V]} {set V UNAVAILABLE}
                    if {$A eq "object_class"} {set Class $V}
                    lappend Values [string map [list "\t" " " "\n" " "] $V]
                }
                puts $F [join $Values "\t"]
                if {$Class eq "cell"} {puts $Cells [join $Values "\t"]}
            }
            close $F;close $Cells
        }
        drc {
            PrNeed check_pg_drc {-output}
            redirect drc.rpt {check_pg_drc -output pg_drc_details.txt}
            # Save the diagnostic copy for the GUI error browser.
            PrStep save_error_block [list save_block]
            PrStep save_error_lib [list save_lib]
        }
        default {error "Unknown action $Action"}
    }
    PgRequireFixed $Macros
    CpSame [PgReadSignature $BaselineMacros] [PgMacroSignature] FINAL_MACRO_IDENTITY
    PgCheckSourceIo $BaselineIo
    puts "CONTINUE_PHASE_COMPLETE: $Action";flush stdout
} Why]} {
    puts stderr "CONTINUE_NATIVE_ERROR: $Why"
    puts stderr $::errorInfo
    exit 2
}
exit 0
