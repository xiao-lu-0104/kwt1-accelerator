# Report-only baseline sensitivity or mapped-pilot SRAM clock/data analysis.
# The zero-hold-uncertainty view is diagnostic, never an accepted constraint set.
# No compile, buffering, mapped-design export, or source-checkpoint mutation.
if {[catch {
set clock_audit 0
if {[info exists ::env(KWT_DC_AUDIT_SRAM_CLOCKS)] && $::env(KWT_DC_AUDIT_SRAM_CLOCKS) eq "1"} {
    set clock_audit 1
}
foreach required {KWT_DC_CHECKPOINT KWT_SRAM_DB_DIR KWT_DC_REPORT_DIR} {
    if {![info exists ::env($required)]} {error "Missing environment variable $required"}
}
set REPORT $::env(KWT_DC_REPORT_DIR)
file mkdir $REPORT
set STD_DB /storage1/2026contest/server1/s1_12usr/lib/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db
if {[info exists ::env(KWT_STDCELL_DB)]} {set STD_DB $::env(KWT_STDCELL_DB)}
set SRAM_DB [file join $::env(KWT_SRAM_DB_DIR) RAMTP1024X16_tt_1p10v_1p10v_25c.db]
foreach required [list $STD_DB $SRAM_DB $::env(KWT_DC_CHECKPOINT)] {
    if {![file isfile $required]} {error "Missing verified input $required"}
}
set target_library [list $STD_DB]
set link_library [concat [list *] $target_library [list $SRAM_DB]]
read_ddc $::env(KWT_DC_CHECKPOINT)
current_design kwt_encoder_12
if {![link]} {error "Checkpoint link failed"}
set clocks [get_clocks -quiet *]
if {[sizeof_collection $clocks] != 1 || [get_object_name $clocks] ne "clk"} {
    error "Audit expects exactly one clock, clk"
}
if {abs([get_attribute $clocks period] - 6.667) > 0.000001} {
    error "Checkpoint clock period differs from 6.667 ns"
}
set macros [get_cells -hierarchical -filter {ref_name == RAMTP1024X16}]
if {[sizeof_collection $macros] != 40} {error "Expected 40 real SRAM macros"}
foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set reference [get_attribute $cell ref_name]
    if {$reference eq {**logic_0**} || $reference eq {**logic_1**}} {continue}
    if {[sizeof_collection [get_lib_cells -quiet */$reference]] != 1} {
        error "Unresolved or ambiguous leaf [get_object_name $cell]: $reference"
    }
}
set macro_inputs [get_pins -of_objects $macros -filter {direction == in && full_name !~ */CLKA && full_name !~ */CLKB}]
if {[sizeof_collection $macro_inputs] == 0} {error "No SRAM data/control inputs"}
set register_inputs [remove_from_collection [all_registers -data_pins] $macro_inputs]

proc kwt_audit_sdc_signature {text} {
    set result {}
    foreach line [split $text "\n"] {
        set line [string trim $line]
        if {$line ne "" && ![string match {#*} $line]} {lappend result $line}
    }
    return $result
}
proc kwt_audit_wns {kind args} {
    set paths [eval get_timing_paths -delay_type $kind -max_paths 1 $args]
    if {[sizeof_collection $paths] == 0} {error "Missing constrained $kind path ($args)"}
    return [get_attribute $paths slack]
}
proc kwt_audit_reports {tag} {
    global REPORT macro_inputs register_inputs
    set setup [kwt_audit_wns max]
    set hold [kwt_audit_wns min]
    set sram_hold [kwt_audit_wns min -to $macro_inputs]
    puts "AUDIT_${tag}_SETUP_WNS: $setup ns"
    puts "AUDIT_${tag}_HOLD_WNS: $hold ns"
    puts "AUDIT_${tag}_SRAM_INPUT_HOLD_WNS: $sram_hold ns"
    report_timing -delay_type min -max_paths 10 -significant_digits 6 > $REPORT/${tag}_hold.rpt
    report_timing -delay_type min -to $macro_inputs -max_paths 10 -significant_digits 6 > $REPORT/${tag}_sram_input_hold.rpt
    report_timing -delay_type max -max_paths 5 -significant_digits 6 > $REPORT/${tag}_setup.rpt
    if {[sizeof_collection $register_inputs] > 0} {
        puts "AUDIT_${tag}_REGISTER_HOLD_WNS: [kwt_audit_wns min -to $register_inputs] ns"
        report_timing -delay_type min -to $register_inputs -max_paths 10 -significant_digits 6 > $REPORT/${tag}_register_hold.rpt
    }
    return [list $setup $hold]
}

puts "AUDIT_MODE: report only; no optimization; no timing signoff; mapped-pilot clock audit = $clock_audit"
puts "AUDIT_CHECKPOINT: $::env(KWT_DC_CHECKPOINT)"
puts "AUDIT_SRAM_CELLS: 40 x RAMTP1024X16"
write_sdc -nosplit $REPORT/baseline.sdc
set fp [open $REPORT/baseline.sdc r]
set baseline_sdc [read $fp]
close $fp
foreach line [split $baseline_sdc "\n"] {
    if {[regexp {^\s*(create_clock|set_clock_uncertainty)\s} $line]} {
        puts "AUDIT_BASELINE_CONSTRAINT: [string trim $line]"
    }
}
report_area > $REPORT/baseline_area.rpt
report_qor > $REPORT/baseline_qor.rpt
check_timing > $REPORT/baseline_check_timing.rpt
set baseline [kwt_audit_reports BASELINE]

if {$clock_audit} {
    set macro_clocks [get_pins -of_objects $macros -filter {full_name =~ */CLKA || full_name =~ */CLKB}]
    if {[sizeof_collection $macro_clocks] != 80} {error "Expected exactly 80 SRAM clock pins"}
    set data_endpoints [add_to_collection $register_inputs $macro_inputs]
    set data_endpoints [add_to_collection $data_endpoints [all_outputs]]
    set data_endpoints [remove_from_collection $data_endpoints $macro_clocks]
    puts "CLOCK_AUDIT_DATA_ENDPOINT_HOLD_WNS: [kwt_audit_wns min -to $data_endpoints] ns"
    puts "CLOCK_AUDIT_SRAM_CLOCK_PIN_HOLD_WNS: [kwt_audit_wns min -to $macro_clocks] ns"
    set macro_outputs [get_pins -of_objects $macros -filter {direction == out}]
    puts "CLOCK_AUDIT_SRAM_READ_HOLD_WNS: [kwt_audit_wns min -through $macro_outputs] ns"
    report_timing -delay_type min -to $data_endpoints -max_paths 10 -significant_digits 6 > $REPORT/data_endpoint_hold.rpt
    report_timing -delay_type min -to $macro_clocks -max_paths 10 -significant_digits 6 > $REPORT/sram_clock_pin_hold.rpt
    report_timing -delay_type min -through $macro_outputs -max_paths 10 -significant_digits 6 > $REPORT/sram_read_hold.rpt
    write_sdc -nosplit $REPORT/clock_audit_after.sdc
    set fp [open $REPORT/clock_audit_after.sdc r]
    set after_sdc [read $fp]
    close $fp
    if {[kwt_audit_sdc_signature $after_sdc] ne [kwt_audit_sdc_signature $baseline_sdc]} {
        error "Constraints changed during report-only clock audit"
    }
    puts "CLOCK_AUDIT_ACCEPTANCE: NONE; all original timing arcs and constraints retained"
    puts "AUDIT_REPORTS: $REPORT"
    puts "KWT_SRAM_CLOCK_AUDIT_COMPLETE"
} else {
# Deliberately change ONLY the in-memory hold uncertainty for sensitivity.
# Setup uncertainty, all IO/path constraints, the netlist and input DDC persist.
# No DDC/netlist is written from this diagnostic view.
puts "AUDIT_SENSITIVITY: hold uncertainty = 0 ns, diagnostic only; baseline remains authoritative"
set_clock_uncertainty -hold 0.0 $clocks
write_sdc -nosplit $REPORT/diagnostic_zero_hold_uncertainty.sdc
set diagnostic [kwt_audit_reports ZERO_HOLD_UNCERTAINTY]
if {abs([lindex $baseline 0] - [lindex $diagnostic 0]) > 0.000001} {
    error "Setup WNS changed during hold-only sensitivity analysis"
}
puts "AUDIT_HOLD_WNS_DELTA: [expr {[lindex $diagnostic 1] - [lindex $baseline 1]}] ns"
puts "AUDIT_ACCEPTANCE: NONE; baseline constraints/status unchanged; hold closure remains pending"
puts "AUDIT_REPORTS: $REPORT"
puts "KWT_HOLD_AUDIT_COMPLETE"
}
} task_error]} {
    puts stderr "KWT_AUDIT_ERROR: $task_error"
    exit 1
}
exit 0
