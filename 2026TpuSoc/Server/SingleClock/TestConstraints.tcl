# Mock collection test: not an EDA execution.
set Here [file dirname [file normalize [info script]]]
set Calls {}
foreach Command {create_clock set_clock_uncertainty set_clock_transition set_false_path set_input_delay set_output_delay set_input_transition set_load} {
    proc $Command {args} [format {lappend ::Calls [linsert $args 0 %s]} $Command]
}
proc get_ports {args} {return [lindex $args end]}
proc get_clocks {args} {return [lindex $args end]}
proc all_clocks {} {return CoreClock}
proc all_inputs {} {return $::Inputs}
proc all_outputs {} {return {CpuPc FetchRequestAddress AxiWriteData}}
proc get_object_name {Object} {return $Object}
proc foreach_in_collection {Variable Objects Body} {uplevel 1 [list foreach $Variable $Objects $Body]}
proc Require {Condition Message} {if {![uplevel 1 [list expr $Condition]]} {error $Message}}
set Inputs {Clock ResetN FetchRequestReady DtcmResponseValid AxiReadData}
foreach Top {TpuNiceAxi E203TpuBackend} {
    set Calls {}
    source [file join $Here Constraints.tcl]
    set ClockCount 0
    set ResetBudgets 0
    set Cuts 0
    set InputBudgets 0
    set OutputBudgets 0
    foreach Call $Calls {
        set Command [lindex $Call 0]
        if {$Command eq "create_clock"} {
            incr ClockCount
            Require {$Call eq {create_clock -name CoreClock -period 6.666667 Clock}} "Wrong clock: $Call"
        }
        if {$Command eq "set_false_path"} {
            incr Cuts
            Require {$Call eq {set_false_path -from ResetN}} "Unexpected cut: $Call"
        }
        if {$Command eq "set_input_delay" || $Command eq "set_output_delay"} {
            Require {[lindex $Call 2] eq "CoreClock"} "Wrong IO clock: $Call"
            Require {[lindex $Call end] ne "Clock"} "Clock port given IO delay"
            if {$Command eq "set_input_delay"} {incr InputBudgets} else {incr OutputBudgets}
            if {[lindex $Call end] eq "ResetN"} {incr ResetBudgets}
        }
    }
    Require {$ClockCount == 1} "Expected one clock"
    Require {$OutputBudgets == 6} "Missing output max/min budgets"
    if {$Top eq "E203TpuBackend"} {
        Require {$Cuts == 1 && $ResetBudgets == 0 && $InputBudgets == 6} "Wrong integrated reset/IO selection"
    } else {
        Require {$Cuts == 0 && $ResetBudgets == 2 && $InputBudgets == 8} "Wrong standalone reset/IO selection"
    }
}
lappend Inputs CpuClock
Require {[catch {source [file join $Here Constraints.tcl]} Message]} "Unexpected second clock accepted"
Require {[string match *second\ clock* $Message]} "Wrong rejection: $Message"
foreach Name {Run.tcl Constraints.tcl Reports.tcl} {
    set F [open [file join $Here $Name] r]
    set Script [read $F]
    close $F
    Require {[info complete $Script]} "Incomplete Tcl: $Name"
}
puts "PASS SINGLE_CLOCK_CONSTRAINTS: one clock, ordinary synchronous IO, reset scope, second-clock rejection; mocks only"
