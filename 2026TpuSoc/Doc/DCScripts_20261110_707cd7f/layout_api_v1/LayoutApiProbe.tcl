# Read installed manuals only. No design/library is opened or modified.
set Required {create_pin_constraint set_block_pin_constraints place_pins}
set Commands {
    create_pin_constraint set_individual_pin_constraints create_pin_guide
    set_block_pin_constraints place_pins check_pin_placement
    report_pin_constraints report_individual_pin_constraints
    get_terminals get_shapes get_layers
    create_pg_mesh_pattern create_pg_macro_conn_pattern
    set_pg_strategy set_pg_strategy_via_rule set_pg_via_master_rule
    check_pg_connectivity check_pg_drc
}
set Summary [open PinApiSummary.txt w]
puts $Summary "SCOPE: installed command documentation only; no design opened or EDA implementation started"
set Missing {}
foreach Name $Commands {
    set Present [expr {[llength [info commands $Name]] > 0}]
    puts $Summary "COMMAND: $Name AVAILABLE: $Present"
    if {!$Present} {
        if {$Name in $Required} {lappend Missing $Name}
        continue
    }
    if {[catch {redirect "${Name}_manual.txt" [list man $Name]} Why]} {
        puts $Summary "MANUAL_ERROR: $Why"
        if {$Name in $Required} {lappend Missing $Name}
        continue
    }
    set F [open "${Name}_manual.txt" r];set M [read $F];close $F
    while {[string first "\b" $M] >= 0} {
        if {![regsub -all ".\b" $M {} M]} {break}
    }
    if {$Name in {create_pin_constraint set_individual_pin_constraints create_pin_guide set_block_pin_constraints}} {
        set Start [string first SYNTAX $M]
        if {$Start < 0} {
            puts $Summary "SYNTAX_UNAVAILABLE"
            if {$Name in $Required} {lappend Missing $Name}
        } else {
            set Tail [string range $M $Start end]
            set End [string first ARGUMENTS $Tail]
            if {$End >= 0} {set Tail [string range $Tail 0 [expr {$End-1}]]}
            puts $Summary [string trim $Tail]
        }
    }
}
puts $Summary "MISSING_REQUIRED: $Missing"
puts $Summary "RESULT: DOCUMENTATION_COLLECTED_NOT_LAYOUT_OR_PG_ACCEPTANCE"
close $Summary
set F [open PinApiSummary.txt r];puts [read $F];close $F
flush stdout
if {[llength $Missing]} {exit 2}
exit 0
