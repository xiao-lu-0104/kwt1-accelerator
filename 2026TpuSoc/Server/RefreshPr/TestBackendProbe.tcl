# Installed-API probe protocol test, no actual physical tool.
set Here [file dirname [file normalize [info script]]]
set Out [lindex $argv 0];file mkdir $Out
file copy -force [file join $Here BackendProbe.tcl] [file join $Out BackendProbe.tcl]
file copy -force [file join $Here .. FinalBackend PrCommon.tcl] [file join $Out PrCommon.tcl]
cd $Out
set F [open BackendProbeConfig.tcl w]
puts $F {set PrDesignLib /new_copy/system_1109.nlib
set PrRefLibs {/new_copy/rvt.ndm /new_copy/private.ndm /new_copy/shared.ndm}}
close $F
proc open_lib P {if {$P ne "/new_copy/system_1109.nlib"} {error "Wrong copy"};return 1}
proc set_ref_libs args {return 1}
proc open_block N {if {$N ne "e203_cpu_top"} {error "Wrong current top"};return 1}
proc link_block {} {return 1}
proc current_block {} {return e203_cpu_top}
proc get_object_name N {return $N}
proc sizeof_collection C {return [llength $C]}
proc foreach_in_collection {V C B} {uplevel 1 [list foreach $V $C $B]}
proc get_cells args {
    set Filter [lindex $args end]
    if {[string first is_unbound $Filter]>=0} {return {}}
    if {[string first RAMSP1024X16 $Filter]>=0} {return [lrepeat 56 private]}
    if {[string first RAMSP4096X16 $Filter]>=0} {return [lrepeat 64 shared]}
    return {std1 std2 macro1}
}
proc get_attribute {Obj A} {
    switch $A {
        core_area_bbox {return {{0 0} {2000 2000}}}
        physical_status {return {unplaced unplaced placed}}
        layer_type {return routing}
        routing_direction {return horizontal}
        pitch {return 0.2}
        period {return 6.66667}
    }
    error "Unknown/unlisted attribute $A"
}
proc get_layers args {return {M1 M2 M3 M4 M5 M6 M7 M8}}
proc all_clocks {} {return CoreClock}
proc list_attributes args {
    if {[lindex $args end] eq "cell"} {puts {physical_status ref_name}} else {puts {layer_type routing_direction pitch}}
}
proc man args {puts "SYNTAX\n [lindex $args 0] -ref_libs -application -class\nDESCRIPTION\n Installed documentation fixture"}
proc redirect {Name Body} {
    rename puts _puts
    proc puts args {lappend ::Captured [join $args " "]}
    set ::Captured {};set Code [catch {uplevel 1 $Body} Why Opts]
    rename puts {};rename _puts puts
    set F [open $Name w];puts $F [join $::Captured \n];close $F
    if {$Code} {return -options $Opts $Why}
}
foreach N {
    read_parasitic_tech set_parasitic_parameters report_parasitic_parameters
    set_ignored_layers create_pg_ring_pattern create_pg_mesh_pattern create_pg_std_cell_conn_pattern
    create_pg_macro_conn_pattern set_pg_strategy set_pg_strategy_via_rule set_pg_via_master_rule
    compile_pg check_pg_connectivity check_pg_drc connect_pg_net create_port create_terminal
    set_fixed_objects set_block_pin_constraints place_pins legalize_placement check_legality
    place_opt clock_opt route_auto route_opt check_routes report_qor report_timing report_constraints
    write_verilog write_def write_gds write_sdc write_parasitics write_sdf
    set_clock_tree_options set_lib_cell_purpose set_app_options set_scenario_status
    report_units report_placement report_design report_clocks
} {proc $N args {return 1}}
rename exit NativeExit
proc exit Code {
    if {$Code!=0} {NativeExit $Code}
    set F [open BackendOverview.txt r];set Text [read $F];close $F
    if {[string first {LEAF_STATUS: physical_status unplaced 2 placed 1} $Text]<0 || [string first {routing_direction horizontal} $Text]<0} {error "Native state evidence missing"}
    set F [open BackendKeySyntax.txt r];set Text [read $F];close $F
    if {[string first {MISSING_COMMANDS: check_parasitic_tech} $Text]<0} {error "Unavailable installed API not recorded"}
    puts "PASS BACKEND_PROBE_PROTOCOL: copy-only, current 120 macros, native placement/layers/manual evidence retained (mock)"
    NativeExit 0
}
source [file join $Out BackendProbe.tcl]
