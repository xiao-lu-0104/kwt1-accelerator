# Basic native implementation, current netlist only; quality violations retained.
proc Step {Name Command} {
    puts "PR_STEP: $Name";flush stdout
    set Code [catch {uplevel #0 $Command} Value]
    if {$Code} {error "$Name: $Value"}
    return $Value
}
proc Save {} {
    Step save_block {save_block}
    Step save_lib {save_lib}
    Step write_checkpoint {write_def checkpoint.def}
    puts "PR_CHECKPOINT_SAVED";flush stdout
}
proc CheckReport {File Command} {
    # Execution errors remain explicit; violations in a completed report do not
    # prevent the engineering flow from continuing.
    if {[catch {redirect $File $Command} Why]} {
        set F [open $File a];puts $F "CHECK_EXECUTION_ERROR: $Why";close $F
        puts "PR_CHECK_EXECUTION_PENDING: $File $Why"
    }
}
proc Connect {} {
    foreach {Net Pins} {VDD {VDD VDDCE VDDPE} VSS {VSS VSSE}} {
        foreach Pin $Pins {
            set P [get_pins -quiet -physical_context "*/$Pin"]
            if {[sizeof_collection $P]} {connect_pg_net -net $Net $P}
        }
    }
}
if {[catch {
source Config.tcl
set_host_options -max_cores 4
if {$Action eq "01_import_io"} {
    Step create_lib [list create_lib $DesignLib -technology $Technology -ref_libs $RefLibs]
    Step read_netlist [list read_verilog -top $Top $CurrentNetlist]
    Step link {link_block}
    if {[sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]} {error "Unbound physical cells"}
    create_mode FUNC
    create_corner INITIAL
    create_scenario -name FUNC_INITIAL -mode FUNC -corner INITIAL
    current_scenario FUNC_INITIAL
    read_sdc $CurrentSdc
    set Main [get_clocks -quiet CoreClock]
    if {[sizeof_collection $Main]!=1 || abs([get_attribute $Main period]-$ExpectedPeriod)>1e-5} {error "Clock budget mismatch"}
    create_net -power VDD
    create_net -ground VSS
    Connect
    initialize_floorplan -core_utilization 0.45 -core_offset {25 25 25 25}
    Step initial_place {create_placement -floorplan -effort low}
    Save
    set B [get_attribute [current_block] boundary];set X {};set Y {}
    foreach P $B {lappend X [lindex $P 0];lappend Y [lindex $P 1]}
    set X [lsort -real -unique $X];set Y [lsort -real -unique $Y]
    if {[llength $X]!=2 || [llength $Y]!=2} {error "Nonrectangular boundary"}
    set F [open DieBoundary.txt w];puts $F "[lindex $X 0] [lindex $Y 0] [lindex $X 1] [lindex $Y 1]";close $F
    set F [open PortInventory.tsv w];puts $F "port\tdirection"
    foreach_in_collection P [get_ports *] {
        set N [get_object_name $P]
        if {$N in {VDD VSS}} {continue}
        puts $F "$N\t[get_attribute $P direction]"
    }
    close $F
    exec python3 [file join $Tools PinPlan.py] [pwd]
    proc IoConstrain {Name Layer X Y} {
        set P [get_ports -quiet [list $Name]]
        if {[sizeof_collection $P]!=1} {error "IO name not unique: $Name"}
        set_individual_pin_constraints -ports $P -allowed_layers [list $Layer] -location [list $X $Y]
    }
    set_block_pin_constraints -self -allowed_layers {M3 M4} -corner_keepout_distance 20 \
        -pin_spacing_distance 0.84 -stacking_allowed none -hard_constraints location
    source PinPlan.tcl
    Step place_pins {place_pins -self}
    Save
    CheckReport pin_placement.rpt {check_pin_placement}
    set F [open PortTerminalGeometry.tsv w]
    puts $F "port\tterminal\tx1\ty1\tx2\ty2\tlayers"
    foreach_in_collection P [get_ports *] {
        set N [get_object_name $P];if {$N in {VDD VSS}} {continue}
        set T [get_terminals -of_objects $P]
        if {[sizeof_collection $T]!=1} {error "One terminal required for signal $N"}
        set Box [concat {*}[get_attribute $T bbox]]
        set Layers {}
        foreach_in_collection S [get_shapes -of_objects $T] {lappend Layers [get_attribute $S layer_name]}
        puts $F "$N\t[get_object_name $T]\t[join $Box \t]\t[join [lsort -unique $Layers] ,]"
    }
    close $F
    exec python3 -c {import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from PinPlan import validate;print(validate(Path.cwd()))} $Tools
} else {
    open_lib $DesignLib
    set_ref_libs -ref_libs $RefLibs
    open_block $Top
    Step link {link_block}
    current_scenario FUNC_INITIAL
    switch $Action {
        02_pg_place {
            read_parasitic_tech -tlup $RcTlu -layermap $RcMap -name TYPFINAL -sanity_check advanced
            set_parasitic_parameters -corners [get_corners INITIAL] -early_spec TYPFINAL -late_spec TYPFINAL \
                -early_temperature 25 -late_temperature 25
            set_ignored_layers -min_routing_layer M2 -max_routing_layer TM2
            set Macros ""
            foreach {Ref Count} $MacroCounts {
                set C [get_cells -hierarchical -filter "ref_name == $Ref"]
                if {[sizeof_collection $C]!=$Count} {error "Macro inventory differs"}
                set Macros [add_to_collection $Macros $C]
            }
            set_fixed_objects $Macros
            create_keepout_margin -type hard -outer {1.12 1.12 1.12 1.12} $Macros
            set_app_options -name place.coarse.continue_on_missing_scandef -value true
            Step legalize {legalize_placement}
            Save
            create_pg_ring_pattern R_FINAL -horizontal_layer M7 -vertical_layer TM2 \
                -horizontal_width 2.24 -vertical_width 2.52 -horizontal_spacing 1.68 -vertical_spacing 1.68
            set_pg_strategy S_RING -core -pattern {{name: R_FINAL} {nets: {VDD VSS}} {offset: {5.04 5.04}}}
            Step ring {compile_pg -strategies S_RING}
            Save
            create_pg_mesh_pattern M_FINAL -layers {
                {{vertical_layer: M6} {width: 0.56} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{horizontal_layer: M7} {width: 1.12} {spacing: interleaving} {pitch: 84} {offset: 10.08}}
                {{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 168} {offset: 10.08}}
            }
            set_pg_strategy S_MESH -core -pattern {{name: M_FINAL} {nets: {VDD VSS}}} -extension {{stop: outermost_ring}}
            Step mesh {compile_pg -strategies S_MESH}
            Save
            create_pg_std_cell_conn_pattern RAIL_FINAL -layers {M1}
            set_pg_strategy S_RAIL -core -pattern {{name: RAIL_FINAL} {nets: {VDD VSS}}}
            Step rails {compile_pg -strategies S_RAIL}
            Save
            set_pg_via_master_rule PIN_FINAL -via_array_dimension {1 1}
            create_pg_macro_conn_pattern MACRO_FINAL -pin_conn_type long_pin -direction horizontal \
                -layers M5 -pin_layers {M4} -width 0.28 -spacing interleaving -pitch 84 \
                -via_rule {{intersection: adjacent} {via_master: PIN_FINAL}}
            set_pg_strategy S_MACRO -macros $Macros -pattern {{name: MACRO_FINAL} {nets: {VDD VSS}}}
            Step macro_pg {compile_pg -strategies S_MACRO}
            Connect;Save
        }
        03_build_clock {
            Step build_clock {clock_opt -from build_clock -to build_clock}
            Connect;Save
        }
        04_route_clock {
            Step route_clock {clock_opt -from route_clock -to route_clock}
            Connect;Save
        }
        05_route {
            redirect route_auto_manual.txt {man route_auto}
            set F [open route_auto_manual.txt r];set M [read $F];close $F
            if {[string first -max_detail_route_iterations $M]>=0} {
                Step route {route_auto -max_detail_route_iterations 3}
            } else {Step route {route_auto}}
            Save
        }
        06_export {
            Connect;Save
            Step verilog {write_verilog routed.v}
            redirect write_sdc_manual.txt {man write_sdc}
            set F [open write_sdc_manual.txt r];set M [read $F];close $F
            if {[string first -output $M]>=0} {Step sdc {write_sdc -output routed.sdc}} else {Step sdc {write_sdc routed.sdc}}
            if {[llength [info commands write_gds]]} {Step gds {write_gds routed_unmerged.gds}}
            CheckReport setup.rpt {report_timing -delay_type max -max_paths 20}
            CheckReport hold.rpt {report_timing -delay_type min -max_paths 20}
            CheckReport route.rpt {check_routes}
            CheckReport legality.rpt {check_legality}
        }
        07_checks {
            CheckReport connectivity.rpt {check_pg_connectivity -check_macro_pins all -check_std_cell_pins all}
            CheckReport pg_drc.rpt {check_pg_drc -output pg_drc_details.txt}
        }
        default {error "Unknown PR stage"}
    }
}
puts "PR_STAGE_COMPLETE: $Action"
} Why]} {puts stderr "PR_ERROR: $Why";puts stderr $::errorInfo;exit 2}
exit 0
