# Native-protocol mock only: exercise the real RegularIo.tcl, not ICC2.
set Here [file dirname [file normalize [info script]]]
set Out [lindex $argv 0];file mkdir $Out;cd $Out
set Mode [lindex $argv 1]
set Ports {clk rst_n test_mode core_csr_clk inspect_core_clk}
foreach Bus {ext2itcm_icb_cmd_wdata ext2dtcm_icb_rsp_rdata mem_icb_cmd_addr ppi_icb_rsp_rdata inspect_pc dpc_r} {
    for {set I 0} {$I<32} {incr I} {lappend Ports "${Bus}\[$I\]"}
}
set Targets [dict create];set Saved 0
proc sizeof_collection C {return [llength $C]}
proc foreach_in_collection {Var C Body} {uplevel 1 [list foreach $Var $C $Body]}
proc get_object_name C {return [lindex $C 0]}
proc get_ports args {
    set Name [lindex $args end]
    if {$Name eq "*"} {return $::Ports}
    return $Name
}
proc get_layers args {return [lindex $args end]}
proc current_block {} {return BLOCK}
proc get_attribute {Object Attr} {
    switch $Attr {
        pitch {return 0.14}
        boundary {return {{0 0} {2050 0} {2050 2050} {0 2050}}}
        direction {return in}
        ref_name {return RAMSP1024X16}
        layer_name {
            if {[string first T: $Object]==0} {return [lindex [dict get $::Targets [string range $Object 2 end]] 0]}
            return M4
        }
        bbox {
            if {[string first T: $Object]==0} {
                lassign [dict get $::Targets [string range $Object 2 end]] L X Y
                if {$::Mode eq "moved"} {set X [expr {$X+10}]}
                return [list [list [expr {$X-0.035}] [expr {$Y-0.035}]] [list [expr {$X+0.035}] [expr {$Y+0.035}]]]
            }
            return {{100 100} {100.2 110}}
        }
    }
    error "Unexpected attribute $Object $Attr"
}
proc get_terminals args {
    if {!$::Saved} {error "Terminal audit happened before checkpoint save"}
    if {$::Mode eq "missing"} {return {}}
    return "T:[lindex [lindex $args end] 0]"
}
proc get_cells args {return {macro0 macro1}}
proc get_pins args {set C [lindex $args end];return [list $C/VDD $C/VSS]}
proc get_shapes args {return "S:[lindex $args end]"}
proc set_individual_pin_constraints args {
    set P [lindex [lindex $args [expr {[lsearch -exact $args -ports]+1}]] 0]
    set L [lindex $args [expr {[lsearch -exact $args -allowed_layers]+1}]]
    set XY [lindex $args [expr {[lsearch -exact $args -location]+1}]]
    dict set ::Targets $P [linsert $XY 0 $L]
    return 1
}
proc set_block_pin_constraints args {return 1}
proc place_pins args {if {[dict size $::Targets]!=[llength $::Ports]} {error "Missing location constraints"};return 1}
proc save_block args {set ::Saved 1;return 1}
proc save_lib args {return 1}
proc write_def File {set F [open $File w];puts $F "MOCK_IO_DEF";close $F;return 1}
proc check_pin_placement args {puts "MOCK_NATIVE_PIN_REPORT";return 1}
proc man args {puts {SYNTAX -ports -allowed_layers -location -self -corner_keepout_distance -pin_spacing_distance -stacking_allowed -hard_constraints -of_objects}}
proc redirect {Name Body} {
    rename puts _puts
    proc puts args {lappend ::RedirectText [join $args " "]}
    set ::RedirectText {};set Code [catch {uplevel 1 $Body} Why Opts]
    rename puts {};rename _puts puts
    set F [open $Name w];puts $F [join $::RedirectText \n];close $F
    if {$Code} {return -options $Opts $Why}
    return $Why
}
source [file join $Here .. FinalBackend PrCommon.tcl]
source [file join $Here RegularIo.tcl]
puts "MOCK_REGULAR_IO_COMPLETE: ports=[dict size $Targets]"
