# Validate port coverage and unchanged numerical budgets with Tcl mocks; not STA.
set Here [file dirname [file normalize [info script]]]
set Inputs {nice_clk nice_rst_n nice_req_valid nice_req_inst nice_req_rs1 nice_req_rs2 nice_rsp_ready nice_icb_cmd_ready nice_icb_rsp_valid nice_icb_rsp_rdata nice_icb_rsp_err}
set Outputs {nice_active nice_mem_holdup nice_req_ready nice_rsp_valid nice_rsp_rdat nice_rsp_err nice_icb_cmd_valid nice_icb_cmd_addr nice_icb_cmd_read nice_icb_cmd_wdata nice_icb_cmd_size nice_icb_rsp_ready}
set Calls {}
proc Require {Condition Message} {if {![uplevel 1 [list expr $Condition]]} {error $Message}}
proc foreach_in_collection {Variable Collection Body} {
    upvar 1 $Variable Item
    foreach Item $Collection {uplevel 1 $Body}
}
proc all_inputs {} {return $::Inputs}
proc all_outputs {} {return $::Outputs}
proc all_clocks {} {return CoreClock}
proc sizeof_collection {Items} {return [llength $Items]}
proc get_object_name {Name} {return $Name}
proc get_ports {Name} {return $Name}
proc get_clocks {Name} {return $Name}
foreach Command {create_clock set_clock_uncertainty set_clock_transition set_input_delay set_input_transition set_output_delay set_load} {
    proc $Command {args} [format {lappend ::Calls [linsert $args 0 %s]} $Command]
}
proc set_false_path {args} {error "Unexpected timing exception"}
proc set_multicycle_path {args} {error "Unexpected multicycle exception"}
source [file join $Here Constraints.tcl]
Require {[lsearch -exact $Calls {create_clock -name CoreClock -period 6.666667 nice_clk}] >= 0} "Wrong clock"
foreach Pair {{-setup 0.200} {-hold 0.100}} {
    Require {[lsearch -exact $Calls [concat set_clock_uncertainty $Pair CoreClock]] >= 0} "Wrong uncertainty"
}
foreach Input [lrange $Inputs 1 end] {
    foreach Pair {{-max 1.000} {-min 0.100}} {
        Require {[lsearch -exact $Calls [concat {set_input_delay -clock CoreClock} $Pair $Input]] >= 0} "Unbudgeted input $Input"
    }
}
foreach Output $Outputs {
    foreach Pair {{-max 1.000} {-min -0.100}} {
        Require {[lsearch -exact $Calls [concat {set_output_delay -clock CoreClock} $Pair $Output]] >= 0} "Unbudgeted output $Output"
    }
}
foreach Name {Constraints.tcl Run.tcl Snapshot.tcl AuditCells.tcl} {
    set F [open [file join $Here $Name] r]
    Require {[info complete [read $F]]} "Incomplete Tcl $Name"
    close $F
}
puts "PASS SHARED_ASIC_CONSTRAINTS: one 150MHz clock, all IO including reset budgeted, no timing cuts; mocks only"
