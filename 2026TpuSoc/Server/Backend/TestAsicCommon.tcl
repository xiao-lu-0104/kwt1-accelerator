# Regression for the actual multi-group scalar/area failures. Mock DC objects.
set Here [file dirname [file normalize [info script]]]
source [file join $Here AsicCommon.tcl]
proc foreach_in_collection {Variable Objects Body} {uplevel 1 [list foreach $Variable $Objects $Body]}
proc sizeof_collection {Objects} {return [llength $Objects]}
proc get_object_name {Object} {return $Object}
proc add_to_collection {Objects Object} {return [concat $Objects $Object]}
proc get_timing_paths {args} {return $::Paths}
proc get_attribute {Object Attribute} {return $::Properties($Object,$Attribute)}
proc get_cells {args} {return {g0 g1 macro constant}}
set Queries 0
proc get_lib_cells {args} {
    incr ::Queries
    return [file tail [lindex $args end]]
}
proc Require {Condition Message} {if {![uplevel 1 [list expr $Condition]]} {error $Message}}
set Paths {p0 p1 p2 p3}
foreach Path $Paths Slack {0.0140842 0.186643 0.186648 -0.120269} {set Properties($Path,slack) $Slack}
set Hold [PathSlack min]
Require {[string is double -strict $Hold] && $Hold == -0.120269} "Global hold must be a scalar minimum including the last group"
Require {[expr {$Hold >= 0}] == 0} "Negative hold must produce FAIL"
Require {[NumericMinimum {10 2}] == 2} "Minimum must use numeric ordering"
Require {[catch {NumericMinimum {}}]} "Empty values must fail"
Require {[catch {NumericMinimum {{0.1 0.2}}}]} "A list must never be treated as one scalar"
Require {[catch {NumericMinimum {0.1 Inf}}]} "Unconstrained/non-finite slack must fail"
set Paths {}
Require {[catch {PathSlack max}]} "Missing constrained paths must fail"
set Properties(g0,ref_name) GATE
set Properties(g1,ref_name) GATE
set Properties(macro,ref_name) RAMSP1024X16
set Properties(constant,ref_name) **logic_0**
set Properties(GATE,area) 2.5
set Properties(RAMSP1024X16,area) 10.0
Require {[LibraryLeafArea] == 15.0} "Area must count all mapped instances including the macro"
Require {$Queries == 2} "Repeated references should use cached library areas"
puts "PASS ASIC_COMMON: numeric worst across groups, invalid/empty slack rejected, mapped leaf area including macros; mock objects only"
