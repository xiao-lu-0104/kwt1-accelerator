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
        audit {
            CpSame [PgReadSignature $BaselineLeaves] [CpLeaves] CURRENT_707CD7F_LEAF_MAP
            set F [open LayerInventory.tsv w]
            puts $F "layer\tattribute\tvalue"
            foreach Layer {M1 M2 M3 M4 M5 M6 M7 TM2 V1 V2} {
                set L [get_layers $Layer]
                foreach A {pitch min_width min_spacing routing_direction} {
                    if {[catch {get_attribute $L $A} V]} {set V UNAVAILABLE}
                    puts $F "$Layer\t$A\t$V"
                }
            }
            close $F
            foreach Command {create_pg_vias set_pg_via_master_rule create_pg_stapling_vias report_app_options} {
                if {[llength [info commands $Command]]} {CpReport "${Command}_manual.txt" [list man $Command]}
            }
            CpSave
        }
        repair {
            CpSame [PgReadSignature $BaselineLeaves] [CpLeaves] CURRENT_707CD7F_LEAF_MAP
            # Add only legal, same-net contacts to existing M1/M2 geometry.
            # No deletion, ignore_drc, spacing relaxation, or replay of unverified source Tcl.
            PrNeed create_pg_vias {-nets -from_layers -to_layers -via_masters -within_bbox -allow_parallel_objects}
            PrNeed set_pg_via_master_rule {-via_array_dimension}
            CpConnect
            PrStep contact_1x1 [list set_pg_via_master_rule CP707_1X1 -via_array_dimension {1 1}]
            PrStep add_m1_m2_contacts [list create_pg_vias -nets {VDD VSS} -from_layers M1 -to_layers M2 \
                -via_masters CP707_1X1 -within_bbox [get_attribute [current_block] core_area_bbox] -allow_parallel_objects]
            CpConnect
            CpSame [PgReadSignature $BaselineLeaves] [CpLeaves] REPAIR_LOGICAL_LEAVES
            CpSave
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
        01_rc {
            PrNeed read_parasitic_tech {-tlup -layermap -name -sanity_check}
            PrNeed set_parasitic_parameters {-corners -early_spec -late_spec -early_temperature -late_temperature}
            PrStep read_rc [list read_parasitic_tech -tlup $RcTlu -layermap $RcMap -name TYP707CONT -sanity_check advanced]
            PrStep bind_rc [list set_parasitic_parameters -corners [get_corners INITIAL] \
                -early_spec TYP707CONT -late_spec TYP707CONT -early_temperature 25 -late_temperature 25]
            PrStep route_layers [list set_ignored_layers -min_routing_layer M2 -max_routing_layer TM2]
            CpSave
            CpReport rc.rpt [list report_parasitic_parameters]
            set F [open rc.rpt r];set Text [read $F];close $F
            if {[string first TYP707CONT $Text]<0} {error "Native RC binding not confirmed"}
        }
        03_place {
            set Option place.coarse.continue_on_missing_scandef
            if {[lsearch -exact [get_app_options $Option] $Option]<0} {error "Installed no-scan option absent"}
            PrStep no_scan_functional [list set_app_options -name $Option -value true]
            PrStep optimize_placement [list place_opt]
            PrStep legalize [list legalize_placement]
            CpConnect;CpSave;CpTiming
            CpReport legality.rpt [list check_legality]
        }
        04_cts {
            PrStep cts_and_optimization [list clock_opt]
            PrStep propagate [list set_propagated_clock [all_clocks]]
            CpConnect;CpSave;CpTiming
            if {[llength [info commands report_clock_qor]]} {CpReport clock_qor.rpt [list report_clock_qor]}
        }
        05_route {
            PrStep route [list route_auto]
            CpConnect;CpSave;CpTiming
            CpReport route_check.rpt [list check_routes]
        }
        06_route_opt {
            PrStep optimize_route [list route_opt]
            CpConnect;CpSave;CpTiming
            CpReport route_check.rpt [list check_routes]
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
            foreach Command {write_parasitics write_sdf write_gds} {
                if {[llength [info commands $Command]]} {CpReport "${Command}_manual.txt" [list man $Command]}
            }
            if {[llength [info commands write_parasitics]]} {CpReport spef_export.log [list write_parasitics -format SPEF -output routed]}
            if {[llength [info commands write_sdf]]} {CpReport sdf_export.log [list write_sdf routed.sdf]}
            if {[llength [info commands write_gds]]} {CpReport gds_export.log [list write_gds routed_unmerged.gds]}
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
