# Separate process, on a disposable checkpoint copy. Never marks violations clean.
source [file join [file dirname [info script]] PrCommon.tcl]
if {[catch {
    source FullConfig.tcl
    PrStep open_check_copy [list open_lib $DesignLib]
    PrStep check_references [list set_ref_libs -ref_libs $RefLibs]
    PrStep check_block [list open_block e203_cpu_top]
    PrStep check_link [list link_block] 1
    if {$CheckKind eq "pg_drc"} {
        PrNeed check_pg_drc {}
        set Command [list check_pg_drc]
    } elseif {$CheckKind eq "pg_connectivity" || $CheckKind eq "pg_connectivity_final"} {
        PrNeed check_pg_connectivity {-check_macro_pins -check_std_cell_pins}
        set Command [list check_pg_connectivity -check_macro_pins all -check_std_cell_pins all]
    } else {error "Unknown PG check $CheckKind"}
    redirect "${CheckKind}.rpt" $Command
    puts "PG_CHECK_EXECUTED: $CheckKind"
    puts "ACCEPTANCE: command executed; inspect actual violations, not signoff"
} Why]} {
    puts stderr $Why
    puts stderr $::errorInfo
    exit 2
}
exit 0
