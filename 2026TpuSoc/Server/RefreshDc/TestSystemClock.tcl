# Exercise actual system constraint block against a mock collection API.
set Here [file dirname [file normalize [info script]]]
set F [open [file join $Here System.tcl] r]
set Text [read $F]
close $F
set Begin [string first {    create_clock -name CoreClock} $Text]
set End [string first {    source [file join $Tools AsicCommon.tcl]} $Text]
if {$Begin<0 || $End<=$Begin} {error "Missing constraint block"}
set Block [string range $Text $Begin [expr {$End-1}]]
proc foreach_in_collection {Name Objects Body} {uplevel 1 [list foreach $Name $Objects $Body]}
proc get_ports {args} {return [lindex $args end]}
proc get_clocks {args} {return [lindex $args end]}
proc get_object_name {Objects} {return $Objects}
proc sizeof_collection {Objects} {return [llength $Objects]}
proc all_clocks {} {return $::Clocks}
proc all_inputs {} {return {clk reset_n request}}
proc all_outputs {} {return {inspect_core_clk core_csr_clk response}}
proc all_fanin {args} {if {$::BadClock} {return {clk data}}; return clk}
proc create_clock {args} {lappend ::Clocks CoreClock; lappend ::Calls [linsert $args 0 create_clock]}
proc create_generated_clock {args} {
    lappend ::Clocks [lindex $args [expr {[lsearch -exact $args -name]+1}]]
    lappend ::Calls [linsert $args 0 create_generated_clock]
}
foreach Command {set_clock_uncertainty set_clock_transition set_input_delay set_input_transition set_output_delay set_load} {
    proc $Command {args} [format {lappend ::Calls [linsert $args 0 %s]} $Command]
}
set Clocks {}; set Calls {}; set BadClock 0
eval $Block
if {[lsort $Clocks] ne [lsort {CoreClock InspectCoreClock CoreCsrClock}]} {error "Wrong clock objects"}
set Loads {}; set Delays {}
foreach Call $Calls {
    if {[lindex $Call 0] eq "set_output_delay"} {lappend Delays [lindex $Call end]}
    if {[lindex $Call 0] eq "set_load"} {lappend Loads [lindex $Call end]}
}
if {$Delays ne {response response}} {error "Clock outputs incorrectly treated as data"}
if {[lsort $Loads] ne [lsort {inspect_core_clk core_csr_clk response}]} {error "Output loads not preserved"}
set Clocks {}; set Calls {}; set BadClock 1
if {![catch {eval $Block} Why] || [string first {not solely forwarded clk} $Why]<0} {
    error "Nonclock fan-in was not rejected"
}
puts "PASS SYSTEM_CLOCK: forwarded clocks only, output loads preserved, data budgets retained, nonclock fan-in rejected (mock API)"
