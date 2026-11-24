foreach p $argv {set f [open $p r];set s [read $f];close $f;if {![info complete $s]} {error "Incomplete Tcl: $p"};puts "TCL_SYNTAX_COMPLETE: $p"}
