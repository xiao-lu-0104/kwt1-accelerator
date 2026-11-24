# Netlist-to-netlist comparison of the exact baseline and hold candidate.
# No RTL interpretation filters, SVF, reset assumptions or compare-point waivers.
proc Record {Key Value} {
    set F [open EquivStatus.tsv a]
    puts $F "$Key\t$Value"
    close $F
    puts "EQUIV_STAGE: $Key $Value"
}
proc RequireTrue {Key Value} {
    Record $Key $Value
    if {![string is boolean -strict $Value] || !$Value} {error "$Key did not return true"}
}
proc ReadStep {Script} {
    set Value [uplevel 1 $Script]
    if {[string is boolean -strict $Value] && !$Value} {error "Read/setup command returned false: $Script"}
}
proc Report {Name args} {
    if {[catch {redirect "${Name}.rpt" [linsert $args 0 $Name]} Why]} {
        Record REPORT_ERROR "$Name $Why"
    }
}
if {[catch {
    if {![info exists synopsys_auto_setup]} {error "Expected setup control unavailable"}
    set synopsys_auto_setup false
    Record AUTO_SETUP false
    if {[info exists hdlin_unresolved_modules]} {set hdlin_unresolved_modules error}
    foreach Var {verification_set_undriven_signals verification_verify_directly_undriven_output hdlin_unresolved_modules} {
        if {[info exists ::$Var]} {Record SETUP_POLICY "$Var [set ::$Var]"}
    }
    foreach Library [list $::env(TPU_STDCELL_DB) $::env(TPU_SRAM_DB)] {
        ReadStep [list read_db -technology_library $Library]
    }
    ReadStep [list read_verilog -r -libname WORK -netlist $::env(TPU_BASELINE_NETLIST)]
    ReadStep [list set_top r:/WORK/e203_subsys_nice_core]
    ReadStep [list read_verilog -i -libname WORK -netlist $::env(TPU_CANDIDATE_NETLIST)]
    ReadStep [list set_top i:/WORK/e203_subsys_nice_core]
    foreach Side {r i} {
        if {[catch {redirect "black_boxes_${Side}.rpt" [list report_black_boxes -$Side]} Why]} {
            error "Cannot report $Side black-box boundary: $Why"
        }
    }
    Report report_setup_status
    RequireTrue MATCH_RETURN [match]
    Report report_matched_points
    Report report_unmatched_points
    set Verified [verify]
    Record VERIFY_RETURN $Verified
    foreach Name {report_failing_points report_aborted_points report_unverified_points} {Report $Name}
    RequireTrue VERIFY_ACCEPTED $Verified
    Record RESULT HOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING
} Why]} {
    Record ERROR $Why
    puts stderr $::errorInfo
    foreach Name {report_failing_points report_aborted_points report_unmatched_points report_unverified_points} {Report $Name}
    catch {save_session FailureSession}
    Record RESULT HOLD_NETLIST_VERIFY_FAILED_OR_INCONCLUSIVE
    exit 2
}
exit 0
