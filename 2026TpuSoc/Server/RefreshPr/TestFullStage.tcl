# Test the actual FullStage.tcl against a mock installed API, not native PR.
set Here [file dirname [file normalize [info script]]]
set Out [lindex $argv 0];file mkdir $Out
foreach {Source Name} [list [file join $Here FullStage.tcl] FullStage.tcl [file join $Here .. FinalBackend PrCommon.tcl] PrCommon.tcl] {file copy -force $Source [file join $Out $Name]}
cd $Out
set F [open FullConfig.tcl w]
puts $F "set Phase [lindex $argv 1]"
puts $F {set DesignLib /new/1109.nlib
set RefLibs {/new/rvt.ndm /new/private.ndm /new/shared.ndm}
set RcTlu foundry_TYP.tluplus
set RcMap correct_1P8M_1TM.map}
close $F
set FailRoute [expr {[llength $argv]>2}]
set Cells {};set Private {};set Shared {};set Refs [dict create]
for {set I 0} {$I<120} {incr I} {
    set N macro$I;lappend Cells $N
    if {$I<56} {lappend Private $N;dict set Refs $N RAMSP1024X16} else {lappend Shared $N;dict set Refs $N RAMSP4096X16}
}
proc sizeof_collection C {return [llength $C]}
proc foreach_in_collection {V C B} {uplevel 1 [list foreach $V $C $B]}
proc get_object_name C {return $C}
proc get_cells args {
    set F [lindex $args end]
    if {[string first is_unbound $F]>=0} {return {}}
    if {[string first RAMSP1024X16 $F]>=0 && [string first RAMSP4096X16 $F]>=0} {return $::Cells}
    if {[string first RAMSP1024X16 $F]>=0} {return $::Private}
    if {[string first RAMSP4096X16 $F]>=0} {return $::Shared}
    return $::Cells
}
proc get_attribute {C A} {
    if {$A eq "period"} {return 6.66667}
    if {$A eq "ref_name"} {return [dict get $::Refs $C]}
    if {$A eq "bbox"} {set I [string range $C 5 end];return [list [list $I 0] [list [expr {$I+1}] 1]]}
    error "Unexpected attribute $A"
}
proc get_clocks args {return CoreClock}
proc get_corners args {return INITIAL}
proc all_clocks {} {return {CoreClock CoreCsrClock InspectCoreClock}}
proc get_layers args {return [lindex $args end]}
proc get_pins args {return pg_pins}
proc man args {puts {SYNTAX -ref_libs -max_cores -tlup -layermap -name -sanity_check -corners -early_spec -late_spec -early_temperature -late_temperature -min_routing_layer -max_routing_layer -self -allowed_layers -horizontal_layer -vertical_layer -horizontal_width -vertical_width -horizontal_spacing -vertical_spacing -layers -pin_conn_type -core -pattern -extension -strategies -via_rule -check_macro_pins -check_std_cell_pins -net -output -format}}
proc redirect {Name Body} {
    rename puts _puts
    proc puts args {lappend ::Captured [join $args " "]}
    set ::Captured {};set Code [catch {uplevel 1 $Body} Why Opts]
    rename puts {};rename _puts puts
    set F [open $Name w];puts $F [join $::Captured \n];close $F
    if {$Code} {return -options $Opts $Why}
}
proc read_parasitic_tech args {return TYP1109}
proc report_parasitic_parameters {} {puts {INITIAL early=TYP1109 late=TYP1109}}
proc route_auto {} {if {$::FailRoute} {return 0};return 1}
proc write_def N {set F [open $N w];puts $F {NETS 1 ;};puts $F {- n + ROUTED M3 ( 0 0 ) ;};puts $F {END NETS};close $F;return 1}
proc write_verilog N {set F [open $N w];puts $F {module e203_cpu_top; endmodule};close $F;return 1}
proc write_sdc args {set F [open [lindex $args end] w];puts $F {create_clock -period 6.66667};close $F;return 1}
foreach N {open_lib set_ref_libs open_block link_block set_host_options set_fixed_objects save_block save_lib current_scenario set_parasitic_parameters set_ignored_layers set_block_pin_constraints place_pins create_pg_ring_pattern create_pg_mesh_pattern create_pg_std_cell_conn_pattern create_pg_macro_conn_pattern set_pg_strategy set_pg_strategy_via_rule compile_pg connect_pg_net place_opt legalize_placement clock_opt set_propagated_clock route_opt} {proc $N args {return 1}}
foreach N {check_pg_connectivity check_pg_drc check_routes check_legality report_qor report_timing report_constraints report_clocks report_clock_qor write_parasitics write_sdf write_gds} {proc $N args {puts {Native fixture report; violations require real report review};return 1}}
source [file join $Out FullStage.tcl]
