# Mock API test of the actual power script; not native power estimation.
set Here [file dirname [file normalize [info script]]]
set Out [lindex $argv 0]
file mkdir $Out
set ::env(NEW_POWER_CASE) $Out
set ::env(TPU_STDCELL_DB) std.db
set ::env(TPU_SRAM_DB) private.db
set ::env(TPU_SYSTEM_DB) shared.db
set ::env(NEW_POWER_DDC) current.ddc
set ::env(NEW_POWER_SAIF) current.saif
set ::env(NEW_POWER_TOOLS) [file join $Out tools]
file mkdir $::env(NEW_POWER_TOOLS)
foreach {Source Name} [list [file join $Here .. Backend AsicCommon.tcl] AsicCommon.tcl [file join $Here .. SystemBackend AreaBreakdown.tcl] AreaBreakdown.tcl] {
    file copy $Source [file join $::env(NEW_POWER_TOOLS) $Name]
}
set Cells {}; set Refs [dict create]; set Calls {}
proc Add {Name Ref} {lappend ::Cells $Name; dict set ::Refs $Name $Ref}
Add u_e203_cpu/u_e203_nice_core/logic BUF
for {set I 0} {$I<56} {incr I} {Add u_e203_cpu/u_e203_nice_core/Macro$I RAMSP1024X16}
for {set I 0} {$I<32} {incr I} {
    Add u_e203_srams/u_e203_itcm_ram/Macro$I RAMSP4096X16
    Add u_e203_srams/u_e203_dtcm_ram/Macro$I RAMSP4096X16
}
Add u_e203_cpu/u_e203_core/reg DFF
Add u_e203_srams/binding BUF
Add other BUF
proc foreach_in_collection {Var Objects Body} {uplevel 1 [list foreach $Var $Objects $Body]}
proc sizeof_collection {Objects} {return [llength $Objects]}
proc get_object_name {Object} {return $Object}
proc get_designs {args} {return e203_cpu_top}
proc get_clocks {args} {return [lindex $args end]}
proc all_clocks {} {return {CoreClock CoreCsrClock InspectCoreClock}}
proc get_attribute {Object Attr} {
    if {$Attr eq "period"} {return 6.666667}
    return [dict get $::Refs $Object]
}
proc get_cells {args} {
    if {[lindex $args 0] eq "-quiet"} {return [lindex $args end]}
    set Filter [lindex $args end]
    if {[regexp {ref_name == ([A-Za-z0-9_]+)} $Filter -> Ref]} {
        set R {}; foreach C $::Cells {if {[dict get $::Refs $C] eq $Ref} {lappend R $C}}; return $R
    }
    return $::Cells
}
proc add_to_collection {A B} {return [concat $A $B]}
proc saif_map {args} {lappend ::Calls map_start; return 1}
proc read_ddc {args} {lappend ::Calls read_ddc; return e203_cpu_top}
proc current_design {args} {return e203_cpu_top}
proc link {} {return 1}
proc write_sdc {args} {
    set F [open [lindex $args end] w]
    puts $F {create_clock -period 6.666667 [get_ports clk]}
    close $F
}
proc redirect {Path Script} {
    set F [open $Path w]
    puts $F {mock report: -auto_map_names supported}
    close $F
    uplevel 1 $Script
}
proc man {args} {return syntax}
proc reset_switching_activity {args} {lappend ::Calls reset_activity}
proc read_saif {args} {
    if {[lsearch -exact $args -auto_map_names]<0 || [lsearch -exact $args SharedTest/Cpu]<0} {error "Wrong current annotation protocol"}
    lappend ::Calls read_current_saif
    return 1
}
foreach Name {report_saif report_power report_units report_constraint} {proc $Name {args} {return 1}}
proc exit {Code} {if {$Code!=0} {error "Actual power script failed with $Code"};set ::Exit $Code}
source [file join $Here Power.tcl]
if {$Calls ne {map_start read_ddc reset_activity read_current_saif}} {error "Wrong mapping/DDC/SAIF lifecycle"}
set F [open [file join $Out ToolStatus.txt] r];set Status [read $F];close $F
if {[string first "TIMING_BUDGETS: UNCHANGED" $Status]<0} {error "Missing immutable constraint evidence"}
puts "PASS CURRENT_POWER_PROTOCOL: original three clocks retained, mapping active before DDC, fresh system SAIF, immutable structure/budgets (mock API)"
