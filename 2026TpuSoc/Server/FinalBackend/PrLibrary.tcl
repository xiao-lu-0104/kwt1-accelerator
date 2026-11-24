source [file join [file dirname [info script]] PrCommon.tcl]
if {[catch {
    source PrLibraryConfig.tcl
    PrRecord SCOPE REFERENCE_LIBRARY_PREPARATION
    PrNeed create_workspace {-technology}
    PrNeed read_db {}
    PrNeed read_lef {}
    PrNeed check_workspace {}
    PrNeed report_design_mismatch {}
    PrNeed report_workspace {}
    PrNeed commit_workspace {-output}
    PrNeed set_current_mismatch_config {}
    PrNeed get_current_mismatch_config {}
    PrStep create_workspace [list create_workspace -technology $PrTechnology $PrWorkspace]
    # Do not generate a prototype library with relaxed checks or placeholder pins.
    PrStep strict_mismatch_policy [list set_current_mismatch_config default]
    set policy [get_current_mismatch_config]
    PrRecord MISMATCH_POLICY $policy
    if {$policy ne "default"} {error "Default workspace mismatch policy required"}
    PrStep read_db [list read_db $PrDb]
    foreach lef $PrLefs {PrStep read_lef [list read_lef $lef]}
    PrRecord STAGE check_workspace
    set checked 0
    redirect check_workspace.rpt {set checked [check_workspace]}
    PrRecord CHECK_WORKSPACE_RETURN $checked
    # T-2022.03-SP2-1 can return an empty Tcl result after a successful check.
    # Require native success and zero-mismatch reports; empty alone proves nothing.
    redirect report_design_mismatch.rpt {report_design_mismatch}
    redirect report_workspace.rpt {report_workspace}
    foreach name {check_workspace report_design_mismatch} {
        set f [open ${name}.rpt r]
        set native($name) [read $f]
        close $f
        if {[regexp -nocase -line {^\s*(Error|Fatal):} $native($name)]} {
            error "Native $name report contains errors"
        }
    }
    if {$checked ne "" && (![string is boolean -strict $checked] || !$checked)} {
        error "Library workspace check returned failure or an unknown value"
    }
    if {![regexp -line {^\s*Workspace check succeeded!\s*$} $native(check_workspace)]} {
        error "Native workspace success marker missing"
    }
    if {![regexp -line {^\s*No mismatches exist on the design\.\s*$} $native(report_design_mismatch)]} {
        error "Native zero-mismatch report required"
    }
    PrRecord CHECK_WORKSPACE_ACCEPTED 1
    PrRecord CHECK_WORKSPACE_EVIDENCE NATIVE_SUCCESS_AND_NO_DESIGN_MISMATCHES
    if {[file exists $PrNdm]} {error "Refusing existing NDM output"}
    PrStep commit_workspace [list commit_workspace -output $PrNdm]
    if {![file isdirectory $PrNdm]} {error "Committed NDM directory was not created"}
    PrRecord NDM $PrNdm
    PrRecord RESULT REFERENCE_LIBRARY_CREATED_REVIEW_PENDING
} why]} {
    PrRecord ERROR $why
    puts stderr $::errorInfo
    PrReport report_design_mismatch
    PrRecord RESULT REFERENCE_LIBRARY_FAILED
    exit 2
}
exit 0
