# Independent checks on disposable copies of the saved new PG checkpoint.
source [file join [file dirname [info script]] PrCommon.tcl]
if {[catch {
    source PgConfig.tcl
    PrStep library [list open_lib $DesignLib]
    PrStep refs [list set_ref_libs -ref_libs $RefLibs]
    PrStep block [list open_block e203_cpu_top]
    PrStep link [list link_block] 1
    PrStep cores [list set_host_options -max_cores 4]
    if {$Phase eq "connectivity"} {
        PrNeed check_pg_connectivity {-check_macro_pins -check_std_cell_pins}
        set Result [redirect connectivity.rpt {check_pg_connectivity -check_macro_pins all -check_std_cell_pins all}]
    } elseif {$Phase eq "drc"} {
        PrNeed check_pg_drc {}
        set Result [redirect drc.rpt {check_pg_drc}]
    } else {error "Unknown independent PG check"}
    set F [open NativeCheckReturn.txt w];puts $F $Result;close $F
    # Preserve the DRC error set in this check copy, not only the core PG library.
    PrStep save_checked_block [list save_block]
    PrStep save_checked_lib [list save_lib]
    PrRecord RESULT "NEW_707CD7F_PG_CHECK_EXECUTED $Phase"
} Why]} {
    puts stderr $::errorInfo
    exit 2
}
exit 0
