# Execute actual packaged Tcl under a protocol mock; not a physical-tool test.
set Tools [lindex $argv 0];set Out [lindex $argv 1];set Kind [lindex $argv 2];set Bad [lindex $argv 3]
file mkdir $Out;cd $Out
set F [open PgConfig.tcl w]
puts $F "set Phase {$Kind}\nset DesignLib {[file join $Out current.nlib]}\nset RefLibs {a.ndm b.ndm c.ndm}\nset ExpectedPeriod 6.66667"
close $F
set Macros {};set Private {};set Shared {};set Cells {};set Refs [dict create]
for {set I 0} {$I<120} {incr I} {
    set N macro$I;lappend Macros $N;lappend Cells $N
    if {$I<56} {lappend Private $N;dict set Refs $N RAMSP1024X16} else {lappend Shared $N;dict set Refs $N RAMSP4096X16}
}
for {set I 0} {$I<1000} {incr I} {lappend Cells c$I;dict set Refs c$I STD}
set Saved {};set Mutated 0;set MeshBlockages {};set LongPin 0;set SingleCut 0
proc sizeof_collection C {return [llength $C]}
proc foreach_in_collection {Var C Body} {uplevel 1 [list foreach $Var $C $Body]}
proc get_object_name C {return [lindex $C 0]}
proc get_cells args {
    set F [lindex $args end]
    if {[string first is_unbound $F]>=0} {return {}}
    if {[string first RAMSP1024X16 $F]>=0 && [string first RAMSP4096X16 $F]>=0} {return $::Macros}
    if {[string first RAMSP1024X16 $F]>=0} {return $::Private}
    if {[string first RAMSP4096X16 $F]>=0} {return $::Shared}
    return $::Cells
}
proc get_clocks args {return CoreClock}
proc current_block {} {return BLOCK}
proc get_attribute {Object Attr} {
    switch $Attr {
        ref_name {return [dict get $::Refs $Object]}
        period {return 6.66667}
        core_area_bbox {return {{25 25} {2050 2050}}}
        layer_name {return M3}
        bbox {
            if {[string first T: $Object]==0} {return {{0 100} {0.07 100.07}}}
            set I [string range $Object 5 end];set X [expr {25+($I%12)*150}];set Y [expr {25+($I/12)*150}]
            if {$::Mutated && $Object eq "macro0"} {set X [expr {$X+1}]}
            return [list [list $X $Y] [list [expr {$X+82.46}] [expr {$Y+111.1314}]]]
        }
    }
    error "Unsupported mock attribute $Object $Attr"
}
proc get_ports args {return {clk rst_n}}
proc get_terminals args {return "T:[lindex $args end]"}
proc get_shapes args {return {}}
proc get_layers args {return [lindex $args end]}
proc get_pins args {return PG_PIN}
proc open_lib args {if {[string first current.nlib $args]<0} {error "Wrong design"};return 1}
foreach Name {set_ref_libs open_block link_block set_host_options set_fixed_objects current_scenario connect_pg_net save_block save_lib} {proc $Name args {return 1}}
proc write_def File {set F [open $File w];puts $F MOCK_PG_DEF;close $F;lappend ::Saved $File;return 1}
proc create_keepout_margin args {
    if {[lindex $args 3] ne {1.12 1.12 1.12 1.12}} {error "Missing hard macro halo"}
    return 1
}
proc legalize_placement args {return 1}
proc check_legality args {if {![file exists legalized.def]} {error "Legality check before save"};puts "MOCK_LEGALITY";return 1}
foreach Name {create_pg_ring_pattern create_pg_std_cell_conn_pattern set_pg_strategy_via_rule} {proc $Name args {return 1}}
proc set_pg_strategy args {
    set Name [lindex $args 0]
    if {$Name eq "S_MESH707"} {
        set Index [lsearch -exact $args -blockage]
        if {$Index<0} {error "Global mesh has no macro exclusion"}
        set ::MeshBlockages [lindex $args [expr {$Index+1}]]
        if {[llength $::MeshBlockages]!=120} {error "Missing macro exclusions"}
        foreach Group $::MeshBlockages {
            if {[lindex $Group 0] ne {layers: M1 M2 M3 M4 M5} || [lindex [lindex $Group 1] 0] ne "polygon:"} {error "Wrong lower-layer exclusion"}
        }
    }
    return 1
}
proc create_pg_mesh_pattern args {
    if {[regexp -all {pitch: 42} $args]!=7 || [string first {pitch: 84} $args]>=0} {error "Mesh pitch requirement failed"}
    return 1
}
proc set_pg_via_master_rule args {
    if {[lindex $args 2] ne {1 1}} {error "Missing requested 1x1 contact"}
    set ::SingleCut 1;return 1
}
proc create_pg_macro_conn_pattern args {
    foreach {Option Value} {-pin_conn_type long_pin -direction horizontal -layers M5 -pin_layers M4 -width 0.28 -pitch 42} {
        set I [lsearch -exact $args $Option]
        if {$I<0 || [lindex $args [expr {$I+1}]] ne $Value} {error "Wrong long-pin adapter: $Option"}
    }
    set ::LongPin 1;return 1
}
proc compile_pg args {
    if {[lindex $args 1] eq "S_MACRO707"} {
        if {![file exists rails.def] || !$::LongPin || !$::SingleCut} {error "Macro stage order incorrect"}
        if {$::Bad eq "move"} {set ::Mutated 1}
    }
    return 1
}
proc check_pg_connectivity args {puts "MOCK_CONNECTIVITY";return 0}
proc check_pg_drc args {puts "MOCK_DRC";return 0}
proc man args {puts {SYNTAX -ref_libs -max_cores -type -outer -horizontal_layer -vertical_layer -horizontal_width -vertical_width -horizontal_spacing -vertical_spacing -layers -pin_conn_type -direction -pin_layers -width -spacing -pitch -via_rule -core -macros -pattern -extension -blockage -via_array_dimension -strategies -check_macro_pins -check_std_cell_pins}}
proc redirect {Name Body} {
    rename puts _puts;proc puts args {lappend ::RedirectText [join $args " "]}
    set ::RedirectText {};set Code [catch {uplevel 1 $Body} Why Opts]
    rename puts {};rename _puts puts
    set F [open $Name w];puts $F [join $::RedirectText \n];close $F
    if {$Code} {return -options $Opts $Why}
    return $Why
}
if {$Kind in {connectivity drc}} {source [file join $Tools PgCheck.tcl]} else {source [file join $Tools PgStage.tcl]}
