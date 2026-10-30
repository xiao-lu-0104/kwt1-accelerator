# ASIC synthesis with actual RAMTP timing/area models.
# First: lc_shell -f syn/compile_kwt_sram_libs.tcl
# Requires verified kwt_sram_pins.vh in KWT_SRAM_CONFIG_DIR (default below).
# Run: dc_shell -f syn/dc_compact.tcl
# TT result is a synthesis check, not a worst-corner / physical timing signoff.
if {[catch {
set ROOT [file normalize [file join [file dirname [info script]] ..]]
if {[info exists ::env(KWT_RTL_ROOT)]} {set ROOT [file normalize $::env(KWT_RTL_ROOT)]}
set DESIGN kwt_encoder_12
set CLK_PER 6.667
set fix_hold 0
if {[info exists ::env(KWT_DC_FIX_HOLD)] && $::env(KWT_DC_FIX_HOLD) eq "1"} {
    set fix_hold 1
    if {![info exists ::env(KWT_DC_CHECKPOINT)]} {error "Hold repair requires a mapped checkpoint"}
}
set hold_pilot 0
if {[info exists ::env(KWT_DC_PILOT_HOLD_NS)]} {
    set pilot_hold_ns $::env(KWT_DC_PILOT_HOLD_NS)
    if {!$fix_hold || ![string is double -strict $pilot_hold_ns]} {
        error "Hold pilot requires checkpoint-based hold repair and an explicit numeric budget"
    }
    if {$pilot_hold_ns < 0 || $pilot_hold_ns >= 1} {
        error "Hold sensitivity pilot budget must be >= 0 and < 1 ns"
    }
    set hold_pilot 1
}
set REPORT [file join $ROOT dc_out_bound]
set DB_DIR [file join $ROOT syn sram_db]
set CONFIG_DIR [file join $ROOT rtl]
set LIBROOT /storage1/2026contest/server1/s1_12usr/lib/S40/smic
set STDCELL $LIBROOT/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1
set STD_DB $STDCELL/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db
if {[info exists ::env(KWT_SRAM_DB_DIR)]} {set DB_DIR $::env(KWT_SRAM_DB_DIR)}
if {[info exists ::env(KWT_SRAM_CONFIG_DIR)]} {set CONFIG_DIR $::env(KWT_SRAM_CONFIG_DIR)}
if {[info exists ::env(KWT_DC_REPORT_DIR)]} {set REPORT $::env(KWT_DC_REPORT_DIR)}
if {[info exists ::env(KWT_STDCELL_DB)]} {set STD_DB $::env(KWT_STDCELL_DB)}
set SRAM_DB [file join $DB_DIR RAMTP1024X16_tt_1p10v_1p10v_25c.db]
foreach required [list $STD_DB $SRAM_DB [file join $CONFIG_DIR kwt_sram_pins.vh]] {
    if {![file exists $required]} {error "Required verified binding input missing: $required"}
}
file mkdir $REPORT
set target_library [list $STD_DB]
# Link-only SRAM: never infer storage or map combinational logic into it.
set link_library [concat [list *] $target_library [list $SRAM_DB]]
set_app_var search_path [concat $search_path [list $CONFIG_DIR [file join $ROOT rtl]]]
set_app_var verilogout_no_tri true
define_design_lib WORK -path [file join $REPORT work]
set resume 0
if {[info exists ::env(KWT_DC_CHECKPOINT)]} {
    set checkpoint [file normalize $::env(KWT_DC_CHECKPOINT)]
    if {![file exists $checkpoint]} {error "Compiled checkpoint missing: $checkpoint"}
    read_ddc $checkpoint
    set resume 1
    puts "RESUME_CHECKPOINT: $checkpoint"
} else {
    analyze -format sverilog -define KWT_ASIC_SRAM -library WORK [glob [file join $ROOT rtl *.v]]
    elaborate $DESIGN -library WORK -architecture verilog
}
current_design $DESIGN
if {![link]} {error "Link failed; refusing incomplete SRAM area/timing reports"}

set macro_lib [get_lib_cells -quiet */RAMTP1024X16]
if {[sizeof_collection $macro_lib] != 1} {error "Expected exactly one RAMTP1024X16 library cell"}
set macro_area [get_attribute $macro_lib area]
if {$macro_area <= 0} {error "RAMTP1024X16 has no positive library area"}
foreach clock_pin {CLKA CLKB} {
    set pins [get_lib_pins -quiet */RAMTP1024X16/$clock_pin]
    if {[sizeof_collection $pins] != 1} {error "Macro clock pin $clock_pin absent from timing library"}
}
set macros [get_cells -hierarchical -filter {ref_name == RAMTP1024X16}]
if {[sizeof_collection $macros] != 40} {
    error "Default encoder needs 40 physical RAMTP1024X16 cells; got [sizeof_collection $macros]"
}
set_dont_touch $macros true

if {!$resume} {
    create_clock -name clk -period $CLK_PER [get_ports clk]
    set_clock_uncertainty 1.0 [get_clocks clk]
    set_clock_transition 0.2 [get_clocks clk]
    set_input_delay -clock clk 0.5 [remove_from_collection [all_inputs] [get_ports clk]]
    set_output_delay -clock clk 0.5 [all_outputs]
    set_load 0.02 [all_outputs]
    # Use actual macro timing, without estimated hierarchical pin delays.
    compile_ultra -no_autoungroup
    # Save BEFORE validation/reporting, so a reporting error can be recovered
    # without repeating synthesis. DDC retains the mapped design/constraints.
    write -hierarchy -format ddc -output $REPORT/${DESIGN}_compiled.ddc
    write_sdc -nosplit $REPORT/${DESIGN}_compiled.sdc
} else {
    set clocks [get_clocks -quiet clk]
    if {[sizeof_collection $clocks] != 1} {error "Checkpoint missing the constrained clk clock"}
    set period [get_attribute $clocks period]
    if {abs($period-$CLK_PER) > 0.000001} {error "Checkpoint clock period differs from $CLK_PER ns"}
}
if {![link]} {error "Post-compile link failed"}
if {$hold_pilot} {
    # This exploratory budget is not a replacement for the original baseline.
    # Keep the old failure and original SDC visible; export only into pilot dir.
    set original_setup [get_timing_paths -delay_type max -max_paths 1]
    set original_hold [get_timing_paths -delay_type min -max_paths 1]
    if {[sizeof_collection $original_setup] == 0 || [sizeof_collection $original_hold] == 0} {
        error "Missing original constrained setup/hold paths"
    }
    set original_setup_wns [get_attribute $original_setup slack]
    set original_hold_wns [get_attribute $original_hold slack]
    write_sdc -nosplit $REPORT/original_baseline.sdc
    report_timing -delay_type min -max_paths 10 -significant_digits 6 > $REPORT/original_baseline_hold.rpt
    puts "CONSTRAINT_SCOPE: PILOT_ONLY; hold budget is an engineering hypothesis, not an official constraint"
    puts "ORIGINAL_SETUP_WNS: $original_setup_wns ns"
    puts "ORIGINAL_HOLD_WNS: $original_hold_wns ns"
    set original_hold_status FAIL
    if {$original_hold_wns >= 0} {set original_hold_status PASS}
    puts "ORIGINAL_HOLD_STATUS: $original_hold_status (original checkpoint, original constraints)"
    puts "PILOT_HOLD_UNCERTAINTY: $pilot_hold_ns ns; setup and IO constraints retained"
    set_clock_uncertainty -hold $pilot_hold_ns [get_clocks clk]
    set pilot_setup [get_timing_paths -delay_type max -max_paths 1]
    if {abs([get_attribute $pilot_setup slack] - $original_setup_wns) > 0.000001} {
        error "Setup WNS changed while applying hold-only pilot budget"
    }
}
if {$fix_hold} {
    # Compare serialized timing budgets before/after optimization. The only
    # added constraint attribute is fix_hold; no further budget changes. In
    # pilot mode the explicitly labelled trial budget was applied just above.
    proc kwt_sdc_timing_budget {path} {
        set fp [open $path r]
        set text [read $fp]
        close $fp
        regsub -all {\\\r?\n[ \t]*} $text { } text
        set signature {}
        foreach line [split $text "\n"] {
            set line [string trim $line]
            if {[regexp {^(create_clock|create_generated_clock|set_clock_uncertainty|set_clock_latency|set_clock_transition|set_input_delay|set_output_delay|set_input_transition|set_driving_cell|set_load|set_false_path|set_multicycle_path|set_min_delay|set_max_delay|set_disable_timing|set_case_analysis|set_ideal_network|set_propagated_clock)\s} $line]} {
                lappend signature $line
            }
        }
        return [lsort $signature]
    }
    set before_setup [get_timing_paths -delay_type max -max_paths 1]
    set before_hold [get_timing_paths -delay_type min -max_paths 1]
    if {[sizeof_collection $before_setup] == 0 || [sizeof_collection $before_hold] == 0} {
        error "Missing constrained setup/hold paths in checkpoint"
    }
    puts "HOLD_BEFORE_SETUP_WNS: [get_attribute $before_setup slack]"
    puts "HOLD_BEFORE_WNS: [get_attribute $before_hold slack]"
    report_timing -delay_type max -max_paths 10 -significant_digits 6 > $REPORT/setup_before_hold.rpt
    report_timing -delay_type min -max_paths 20 -significant_digits 6 > $REPORT/hold_before.rpt
    report_area > $REPORT/area_before_hold.rpt
    write_sdc -nosplit $REPORT/hold_before.sdc
    set budget_before [kwt_sdc_timing_budget $REPORT/hold_before.sdc]
    set_fix_hold [get_clocks clk]
    # Synopsys DC User Guide U-2022.12-SP3, "Disabling the Cost Function": use compile for
    # -only_hold_time; compile_ultra does not support this option.
    compile -incremental_mapping -only_hold_time
    write -hierarchy -format ddc -output $REPORT/${DESIGN}_hold_attempt.ddc
    write_sdc -nosplit $REPORT/hold_after.sdc
    if {[kwt_sdc_timing_budget $REPORT/hold_after.sdc] ne $budget_before} {
        error "Timing budget changed during hold repair; inspect hold_before.sdc and hold_after.sdc"
    }
    if {![link]} {error "Post-hold-repair link failed"}
}
set macros [get_cells -hierarchical -filter {ref_name == RAMTP1024X16}]
if {[sizeof_collection $macros] != 40} {error "SRAM count changed during synthesis"}
foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set reference [get_attribute $cell ref_name]
    # DC represents tied-low/high nets with built-in constant pseudo-cells.
    # These exact two names are not Liberty cells. Keep all other references
    # subject to the real-library check (including GTECH and missing macros).
    if {$reference eq {**logic_0**} || $reference eq {**logic_1**}} {continue}
    if {[sizeof_collection [get_lib_cells -quiet */$reference]] == 0} {
        error "Unmapped/unresolved leaf [get_object_name $cell], reference $reference"
    }
}
report_reference -hierarchy > $REPORT/references.rpt
report_qor > $REPORT/qor.rpt
report_area -hierarchy > $REPORT/area.rpt
report_area > $REPORT/area_total.rpt
report_timing -max_paths 20 -delay_type max -significant_digits 6 > $REPORT/timing_max.rpt
report_timing -max_paths 10 -delay_type min -significant_digits 6 > $REPORT/timing_min.rpt
set macro_outputs [get_pins -of_objects $macros -filter {direction == out}]
if {[sizeof_collection $macro_outputs] == 0} {error "No macro read-data pins found"}
set macro_paths [get_timing_paths -through $macro_outputs -max_paths 1]
if {[sizeof_collection $macro_paths] == 0} {error "No constrained path through macro read outputs"}
report_timing -through $macro_outputs -max_paths 20 > $REPORT/timing_sram_read.rpt
check_timing > $REPORT/check_timing.rpt
report_power > $REPORT/power_estimate_no_saif.rpt
report_clock_gating > $REPORT/clock_gating.rpt
report_constraint -all_violators > $REPORT/violators.rpt
check_design > $REPORT/check_design.rpt
write -hierarchy -format verilog -output $REPORT/${DESIGN}_netlist.v
write_sdc -nosplit $REPORT/${DESIGN}.sdc
write_sdf -version 3.0 $REPORT/${DESIGN}.sdf
write -hierarchy -format ddc -output $REPORT/${DESIGN}.ddc

set fp [open $REPORT/area_total.rpt r]
set text [read $fp]
close $fp
if {![regexp {Total cell area:\s+([0-9.]+)} $text -> area]} {error "No total cell area in report"}
set sram_area [expr {40 * $macro_area}]
set paths [get_timing_paths -delay_type max -max_paths 1]
if {[sizeof_collection $paths] == 0} {error "No constrained setup path"}
set wns [get_attribute $paths slack]
set area_status FAIL
if {$area <= 2250000} {set area_status PASS}
set setup_status FAIL
if {$wns >= 0} {set setup_status PASS}
set hold_paths [get_timing_paths -delay_type min -max_paths 1]
set hold_wns unavailable
set hold_status UNAVAILABLE
if {[sizeof_collection $hold_paths] > 0} {
    set hold_wns [get_attribute $hold_paths slack]
    set hold_status FAIL
    if {$hold_wns >= 0} {set hold_status PASS}
}
puts "================ BOUND SRAM SYNTHESIS ================"
puts "DESIGN: $DESIGN; PERIOD: $CLK_PER ns; CORNER: TT 1.1V 25C"
if {$hold_pilot} {
    puts "CONSTRAINT_SCOPE: PILOT_ONLY (hold uncertainty $pilot_hold_ns ns; not original-budget closure)"
}
puts "SRAM_CELLS: 40 x RAMTP1024X16; CAPACITY: 80 KiB"
puts [format "SRAM_LIBRARY_AREA: %.2f um^2" $sram_area]
puts [format "TOTAL_CELL_AREA_INCLUDING_SRAM: %.2f um^2 (%.4f mm^2)" $area [expr {$area/1.0e6}]]
puts "AREA_LIMIT_STATUS: $area_status (2250000 um^2 cell-area budget; physical overhead not yet included)"
puts [format "SETUP_WNS: %.3f ns" $wns]
puts "SETUP_STATUS: $setup_status (TT synthesis only)"
puts "HOLD_WNS: $hold_wns"
puts "HOLD_STATUS: $hold_status (TT synthesis only)"
if {$fix_hold} {
    set repair_status FAIL
    if {$area_status eq "PASS" && $setup_status eq "PASS" && $hold_status eq "PASS"} {set repair_status PASS}
    if {$hold_pilot} {
        puts "PILOT_HOLD_REPAIR_STATUS: $repair_status"
        puts "ORIGINAL_BUDGET_CLOSURE: NOT_ESTABLISHED; original baseline hold WNS $original_hold_wns ns"
    } else {
        puts "HOLD_REPAIR_STATUS: $repair_status"
    }
}
puts "REPORTS: $REPORT"
puts "Power has no measured activity; this run is not final power/timing signoff."
puts "KWT_DC_COMPLETE"
} task_error]} {
    puts stderr "KWT_ERROR: $task_error"
    exit 1
}
exit 0
