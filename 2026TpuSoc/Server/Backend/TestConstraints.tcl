# Constraint-selection unit test with mock collections. NOT an EDA execution.
set Here [file dirname [file normalize [info script]]]
source [file join $Here AsicCommon.tcl]
set Calls {}
foreach Command {create_clock set_clock_uncertainty set_clock_transition set_false_path set_input_delay set_output_delay set_input_transition set_load set_dont_touch set_max_delay set_min_delay group_path} {
    proc $Command {args} [format {lappend ::Calls [linsert $args 0 %s]} $Command]
}
proc get_ports {args} {return [lindex $args end]}
proc get_clocks {args} {return [lindex $args end]}
proc all_clocks {} {return {TpuClock CpuClock}}
proc all_inputs {} {return {Clock CpuClock ResetN FetchRequestReady DtcmResponseValid AxiReadData}}
proc all_outputs {} {return {CpuPc FetchRequestAddress AxiWriteData}}
proc get_object_name {Object} {return $Object}
proc sizeof_collection {Objects} {return [llength $Objects]}
proc add_to_collection {Objects Object} {return [concat $Objects $Object]}
proc foreach_in_collection {Variable Objects Body} {uplevel 1 [list foreach $Variable $Objects $Body]}
proc get_pins {args} {
    set Cell [lindex $args end]
    return [list $Cell/D $Cell/CK $Cell/RN]
}
set Cells {}
foreach Channel {RequestChannel ResponseChannel} {
    foreach Name {RequestSynchronizer AcknowledgeSynchronizer} {
        foreach Bit {0 1} {lappend Cells [format {%s/%s_reg[%d]} $Channel $Name $Bit]}
    }
    foreach Name {SourcePayload DestinationData} {
        foreach Bit {0 1 2} {lappend Cells [format {%s/%s_reg[%d]} $Channel $Name $Bit]}
    }
}
proc FindCells {Pattern} {
    set Result {}
    foreach Cell $::Cells {if {[regexp $Pattern $Cell]} {lappend Result $Cell}}
    return $Result
}
proc Require {Condition Message} {if {![uplevel 1 [list expr $Condition]]} {error $Message}}
set Top E203Tpu
set CpuPeriod 20.000000
source [file join $Here AsicConstraints.tcl]
source [file join $Here AsicCdc.tcl]
set Cuts 0
set Domains {}
set Budgets {}
foreach Call $Calls {
    set Command [lindex $Call 0]
    if {$Command eq "set_false_path"} {
        incr Cuts
        if {[lindex $Call 1] eq "-to"} {
            set Pin [lindex [lindex $Call 2] 0]
            Require {[regexp {(RequestSynchronizer|AcknowledgeSynchronizer)_reg\[0\]/D$} $Pin]} "Unexpected CDC cut: $Pin"
        } else {
            Require {$Call eq {set_false_path -from ResetN}} "Unexpected source cut: $Call"
        }
    }
    if {$Command eq "set_input_delay" || $Command eq "set_output_delay"} {
        dict set Domains [lindex $Call end] [lindex $Call 2]
    }
    if {$Command eq "set_max_delay"} {
        lappend Budgets [lindex $Call 1]
        foreach Pin [lindex $Call 4] {Require {[string match */CK $Pin]} "CDC startpoint must be a clock pin"}
        foreach Pin [lindex $Call 6] {Require {[string match */D $Pin]} "CDC endpoint must be a data pin"}
    }
}
Require {$Cuts == 5} "Expected reset plus precisely four stage-0 D cuts"
Require {[dict get $Domains FetchRequestReady] eq "CpuClock"} "Fetch input in wrong domain"
Require {[dict get $Domains DtcmResponseValid] eq "CpuClock"} "DTCM input in wrong domain"
Require {[dict get $Domains CpuPc] eq "CpuClock"} "CPU output in wrong domain"
Require {[dict get $Domains AxiReadData] eq "TpuClock"} "AXI input in wrong domain"
Require {[dict get $Domains AxiWriteData] eq "TpuClock"} "AXI output in wrong domain"
Require {$Budgets eq {6.666667 20.000000}} "Wrong CDC receive-domain budgets"
foreach Name {RunAsic.tcl CompileSpLib.tcl AsicConstraints.tcl AsicCdc.tcl AsicCommon.tcl AsicReports.tcl ReportCheckpoint.tcl} {
    set F [open [file join $Here $Name] r]
    set Script [read $F]
    close $F
    Require {[info complete $Script]} "Incomplete Tcl script: $Name"
}
set Calls {}
set Top TpuNiceAxi
source [file join $Here AsicConstraints.tcl]
set ResetBudget 0
foreach Call $Calls {
    Require {[lindex $Call 0] ne "set_false_path"} "Standalone reset must not be cut"
    if {[lindex $Call 0] eq "set_input_delay" && [lindex $Call end] eq "ResetN"} {incr ResetBudget}
}
Require {$ResetBudget == 2} "Standalone reset requires both max and min input budgets"
puts "PASS CONSTRAINT_SELECTION: CPU/AXI domains, four stage-0 cuts, payload budgets, standalone reset constrained; mock collections only"
