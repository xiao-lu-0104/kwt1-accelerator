# Actual accelerator equivalence attempt. No reset constraints, forced constants,
# don't-verify points, or added black boxes. Foundry macro semantics stay external.
proc Record {key value} {
    set f [open FormalStatus.tsv a]
    puts $f "$key\t$value"
    close $f
    puts "FORMAL_STAGE: $key $value"
}
proc ReadStep {label script} {
    Record STAGE $label
    set value [uplevel 1 $script]
    if {[string is boolean -strict $value] && !$value} {
        error "$label returned false"
    }
    return $value
}
proc Report {name args} {
    if {![llength [info commands $name]]} {
        Record REPORT_UNAVAILABLE $name
        return
    }
    set file "${name}.rpt"
    if {[catch {redirect $file [linsert $args 0 $name]} reason]} {
        Record REPORT_ERROR "$name $reason"
    } else {
        Record REPORT_SAVED $file
    }
}
# Diagnose the native failure without changing matching, constraints or results.
# Save the session/patterns before analysis, which may reach the process time cap.
proc FailureCommand {name options output} {
    if {![llength [info commands $name]]} {
        Record DIAGNOSTIC_UNAVAILABLE $name
        return
    }
    set manualFile "${name}_manual.txt"
    if {[catch {redirect $manualFile [list man $name]} why]} {
        Record DIAGNOSTIC_ERROR "$name manual: $why"
        return
    }
    set f [open $manualFile r]
    set manual [read $f]
    close $f
    while {[string first "\b" $manual] >= 0} {
        if {![regsub -all ".\b" $manual {} manual]} {break}
    }
    if {[string first SYNTAX $manual] < 0} {
        Record DIAGNOSTIC_ERROR "$name installed syntax unavailable"
        return
    }
    foreach option $options {
        if {[string match -* $option] && [string first $option $manual] < 0} {
            Record DIAGNOSTIC_ERROR "$name installed manual does not confirm $option"
            return
        }
    }
    Record DIAGNOSTIC_START $name
    if {[catch {redirect $output [linsert $options 0 $name]} value]} {
        Record DIAGNOSTIC_ERROR "$name $value"
    } elseif {[string is boolean -strict $value] && !$value} {
        Record DIAGNOSTIC_ERROR "$name returned false; inspect $output"
    } else {
        Record DIAGNOSTIC_COMPLETE "$name $output"
    }
}
proc DiagnoseFailure {} {
    Record DIAGNOSTIC_POLICY NO_MATCH_OR_STATE_CHANGES_NATIVE_VERIFY_RESULT_RETAINED
    file mkdir FailureEvidence
    FailureCommand save_session [list FailureSession] save_session.rpt
    FailureCommand write_failing_patterns [list -verilog FailureEvidence/failing] write_failing_patterns.rpt
    FailureCommand analyze_points [list -failing] analyze_points.rpt
    FailureCommand report_analysis_results [list -summary] report_analysis_results.rpt
}
proc SetupSnapshot {phase} {
    foreach name {synopsys_auto_setup verification_set_undriven_signals verification_verify_directly_undriven_output hdlin_ignore_full_case hdlin_ignore_parallel_case svf_ignore_unqualified_fsm_information} {
        if {[info exists ::$name]} {Record SETUP_POLICY "$phase $name [set ::$name]"}
    }
}
if {[catch {
    source FormalConfig.tcl
    Record TOP $FormalTop
    Record SCOPE ACCELERATOR_ONLY
    if {![info exists FormalSvf] || ![file isfile $FormalSvf]} {
        error "Validated accelerator SVF snapshot is required"
    }
    if {![info exists synopsys_auto_setup]} {
        error "Installed Formality does not expose the expected setup control"
    }
    # Load only synthesis guidance. Keep conservative verification policies;
    # do not enable the automatic setup mode that also changes other policies.
    set synopsys_auto_setup false
    Record AUTO_SETUP DISABLED_GUIDANCE_ONLY
    SetupSnapshot BEFORE_SVF
    Record GUIDANCE $FormalSvf
    Record STAGE read_guidance
    set guided [ReadStep read_guidance [list set_svf $FormalSvf]]
    Record GUIDANCE_READ_RETURN $guided
    if {![string is boolean -strict $guided] || !$guided} {
        error "Accelerator synthesis guidance did not load successfully"
    }
    SetupSnapshot AFTER_SVF
    Record MEMORY_POLICY SAME_FOUNDRY_DB_INTERFACES_EXTERNAL_MACRO_SEMANTICS
    # If supported, reject undeclared modules instead of creating extra boxes.
    if {[info exists hdlin_unresolved_modules]} {
        set hdlin_unresolved_modules error
        Record UNRESOLVED_POLICY ERROR
    } else {
        Record UNRESOLVED_POLICY DEFAULT_UNCHANGED_REQUIRES_BLACKBOX_REPORT_REVIEW
    }
    foreach library $FormalLibraries {
        ReadStep read_technology_library [list read_db -technology_library $library]
    }
    Record STAGE confirm_systemverilog_reader
    if {![llength [info commands read_sverilog]]} {
        error "Native read_sverilog command is unavailable; reference RTL was not loaded"
    }
    redirect read_sverilog_manual.txt {man read_sverilog}
    set f [open read_sverilog_manual.txt r]
    set manual [read $f]
    close $f
    while {[string first "\b" $manual] >= 0} {
        if {![regsub -all ".\b" $manual {} manual]} {break}
    }
    foreach option {-r -libname -define} {
        if {[string first $option $manual] < 0} {
            error "Installed read_sverilog manual does not confirm $option"
        }
    }
    Record REFERENCE_LANGUAGE SYSTEMVERILOG
    Record REFERENCE_READER read_sverilog
    ReadStep read_reference [list read_sverilog -r -libname WORK \
        -define {SYNTHESIS TPU_SRAM_MODEL} $FormalSources]
    if {![info exists FormalReviewedArrayWarning] || $FormalReviewedArrayWarning ne "FMR_ELAB-147"} {
        error "Exact prior array-warning review is required before acknowledging an interpretation message"
    }
    # This acknowledges an interpretation risk, not index reachability or
    # equivalence. No compare point or state is constrained or waived.
    set_mismatch_message_filter -warn FMR_ELAB-147
    Record INTERPRETATION_WARNING FMR_ELAB-147
    Record ARRAY_INDEX_SAFETY NOT_PROVED
    ReadStep reference_top [list set_top "r:/WORK/$FormalTop"]
    ReadStep read_implementation [list read_verilog -i -libname WORK -netlist $FormalNetlist]
    ReadStep implementation_top [list set_top "i:/WORK/$FormalTop"]
    # Native reports are retained even if some report commands/options differ.
    foreach name {report_black_boxes report_setup_status} {Report $name}
    if {[llength [info commands report_black_boxes]]} {
        foreach container {r i} {
            if {[catch {redirect "black_boxes_${container}.rpt" \
                [list report_black_boxes -$container]} why]} {
                Record BLACKBOX_CONTAINER_REPORT_ERROR "$container $why"
            }
        }
    }
    Record STAGE match
    set matched [match]
    Record MATCH_RETURN $matched
    Report report_matched_points
    Report report_unmatched_points
    if {![string is boolean -strict $matched] || !$matched} {
        error "Match did not return true; inspect matching reports"
    }
    Record STAGE verify
    set verified [verify]
    Record VERIFY_RETURN $verified
    SetupSnapshot AFTER_VERIFY
    FailureCommand report_guidance [list -summary] guidance_summary.rpt
    foreach name {report_failing_points report_aborted_points report_unverified_points} {Report $name}
    if {![string is boolean -strict $verified] || !$verified} {
        DiagnoseFailure
        error "Verify did not return true; failure or inconclusive result requires review"
    }
    Record RESULT TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING
} reason]} {
    Record ERROR $reason
    puts stderr $::errorInfo
    foreach name {report_failing_points report_aborted_points report_unmatched_points report_black_boxes} {Report $name}
    Record RESULT ATTEMPT_FAILED_OR_INCONCLUSIVE
    exit 2
}
exit 0
