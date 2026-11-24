# Execute the real Place.tcl with a simulated ICC2 API, not a real physical result.
set Here [file dirname [file normalize [info script]]]
set Out [lindex $argv 0]
file mkdir $Out
file copy -force [file join $Here Place.tcl] [file join $Out Place.tcl]
file copy -force [file join $Here .. FinalBackend PrCommon.tcl] [file join $Out PrCommon.tcl]
cd $Out
set F [open CurrentConfig.tcl w]
puts $F {set PrTechnology current.tf
set PrDesignLib new1109.nlib
set PrNetlist current1109.v
set PrSdc current1109.sdc
set PrExpectedClockPeriod 6.66667
set PrRefLibs {rvt.ndm private.ndm shared.ndm}
set PrPowerPins {VDD VDDCE VDDPE}
set PrGroundPins {VSS VSSE}}
close $F
set Cells {}; set Private {}; set Shared {}; set Refs [dict create]; set Calls {}
set MockPeriod 6.66667
if {[llength $argv]>1} {set MockPeriod [lindex $argv 1]}
for {set I 0} {$I<100000} {incr I} {lappend Cells c$I; dict set Refs c$I STD}
for {set I 0} {$I<120} {incr I} {
    set N macro$I; lappend Cells $N
    if {$I<56} {lappend Private $N;dict set Refs $N RAMSP1024X16} else {lappend Shared $N;dict set Refs $N RAMSP4096X16}
}
proc sizeof_collection C {return [llength $C]}
proc foreach_in_collection {Var C Body} {uplevel 1 [list foreach $Var $C $Body]}
proc get_object_name C {return $C}
proc get_cells args {
    set F [lindex $args end]
    if {[string first is_unbound $F]>=0} {return {}}
    if {[string first RAMSP1024X16 $F]>=0 && [string first RAMSP4096X16 $F]>=0} {return [concat $::Private $::Shared]}
    if {[string first RAMSP1024X16 $F]>=0} {return $::Private}
    if {[string first RAMSP4096X16 $F]>=0} {return $::Shared}
    return $::Cells
}
proc get_attribute {C A} {
    switch $A {
        ref_name {return [dict get $::Refs $C]}
        period {return $::MockPeriod}
        core_area_bbox {return {{0 0} {2000 2000}}}
        bbox {
            set I [string range $C 5 end];set X [expr {($I%12)*150}];set Y [expr {($I/12)*150}]
            return [list [list $X $Y] [list [expr {$X+82.46}] [expr {$Y+111.1314}]]]
        }
    }
    error "Unexpected attribute $A"
}
proc man args {puts {SYNTAX -technology -ref_libs -top -name -mode -corner -core_utilization -core_offset -power -ground -net -physical_context -floorplan -effort -hard_macro_overlap -max_cores}}
proc redirect {Name Body} {
    rename puts _puts
    proc puts args {lappend ::RedirectText [join $args " "]}
    set ::RedirectText {};set Code [catch {uplevel 1 $Body} Why Opts]
    rename puts {};rename _puts puts
    set F [open $Name w];puts $F [join $::RedirectText \n];close $F
    if {$Code} {return -options $Opts $Why}
}
proc create_lib args {file mkdir [lindex $args 0];return 1}
proc read_verilog args {
    if {$args ne {-top e203_cpu_top current1109.v}} {error "Wrong design source"}
    return 1
}
proc read_sdc File {if {$File ne "current1109.sdc"} {error "Wrong SDC"};return 1}
proc get_clocks args {return CoreClock}
proc get_pins args {return PG_PIN}
proc current_block {} {return e203_cpu_top}
proc write_def Name {set F [open $Name w];puts $F {DESIGN e203_cpu_top ;};close $F;return 1}
proc report_placement args {puts {Total hard macro to hard macro overlaps: 0}}
proc report_units args {puts {length : 1.00um}}
foreach N {link_block create_mode create_corner create_scenario current_scenario initialize_floorplan create_net connect_pg_net create_placement set_host_options save_block save_lib report_design report_clocks report_design_mismatch} {
    proc $N args "lappend ::Calls \[list $N \$args\];return 1"
}
rename exit NativeExit
proc exit Code {
    if {$Code!=0} {NativeExit $Code}
    if {![file exists placed_1109.def] || [llength $::Calls]<10} {error "Native protocol incomplete"}
    puts "PASS NEW_1109_FULL_SYSTEM_PLACE_PROTOCOL: 120 macros, current netlist/SDC, saved initial and placed DEF (mock)"
    NativeExit 0
}
source [file join $Out Place.tcl]
