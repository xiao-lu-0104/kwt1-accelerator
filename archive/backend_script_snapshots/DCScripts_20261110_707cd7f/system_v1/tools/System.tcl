# Fresh CPU/ICB/shared-TCM mapping around the byte-identical frozen accelerator.
proc FrozenAccelerator {} {
    set Prefix u_e203_cpu/u_e203_nice_core/
    set Result [dict create]
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        set Name [get_object_name $Cell]
        if {[string first $Prefix $Name]!=0} {continue}
        set Ref [get_attribute $Cell ref_name]
        if {$Ref in {**logic_0** **logic_1**}} {continue}
        dict set Result [string range $Name [string length $Prefix] end] $Ref
    }
    if {[dict size $Result]<1000} {error "Incomplete frozen accelerator signature"}
    return $Result
}
proc CheckMacroCounts {} {
    foreach {Ref Expected} {RAMSP1024X16 56 RAMSP4096X16 64} {
        set Count [sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]
        if {$Count!=$Expected} {error "Macro count $Ref expected=$Expected actual=$Count"}
    }
}
if {[catch {
    set Out $::env(TPU_SYSTEM_OUT)
    set Tools $::env(TPU_SYSTEM_TOOLS)
    cd $Out
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB) $::env(TPU_SYSTEM_DB)]]
    define_design_lib WORK -path [file join $Out work]
    set_app_var verilogout_no_tri true
    set_host_options -max_cores 4
    set_svf [file join $Out system_guidance.svf]
    # Preserve RTL-to-mapped names for the subsequent activity annotation stage.
    saif_map -start
    source [file join [file dirname $Out] Sources.tcl]
    set_app_var search_path [concat $search_path $Includes]
    if {![analyze -format sverilog -define {SYNTHESIS FPGA FPGA_SOURCE} -library WORK $Sources]} {
        error "System source analysis failed"
    }
    elaborate e203_cpu_top -library WORK
    current_design e203_cpu_top
    if {![link]} {error "System link failed"}
    CheckMacroCounts
    set Scope [get_cells -quiet u_e203_cpu/u_e203_nice_core]
    if {[sizeof_collection $Scope]!=1} {error "Missing frozen accelerator boundary"}
    set Frozen [FrozenAccelerator]
    set F [open [file join [file dirname $Out] ExpectedAccelerator.tsv] r]
    gets $F Header
    set Expected [dict create]
    while {[gets $F Line]>=0} {
        set Fields [split $Line "\t"]
        if {[llength $Fields]!=3} {error "Invalid expected accelerator inventory"}
        lassign $Fields Name Ref Region
        if {$Ref ni {**logic_0** **logic_1**}} {dict set Expected $Name $Ref}
    }
    close $F
    if {[dict size $Frozen]!=[dict size $Expected]} {error "Integrated accelerator differs from reviewed candidate count"}
    dict for {Name Ref} $Expected {
        if {![dict exists $Frozen $Name] || [dict get $Frozen $Name] ne $Ref} {
            error "Integrated accelerator differs from candidate: $Name"
        }
    }
    set_dont_touch $Scope true
    foreach Ref {RAMSP1024X16 RAMSP4096X16} {
        set_dont_touch [get_cells -hierarchical -filter "ref_name == $Ref"] true
    }
    create_clock -name CoreClock -period 6.666667 [get_ports clk]
    set_clock_uncertainty -setup 0.200 [all_clocks]
    set_clock_uncertainty -hold 0.100 [all_clocks]
    set_clock_transition 0.100 [all_clocks]
    foreach_in_collection Port [all_inputs] {
        if {[get_object_name $Port] eq "clk"} {continue}
        set_input_delay -clock CoreClock -max 1.000 $Port
        set_input_delay -clock CoreClock -min 0.100 $Port
        set_input_transition 0.100 $Port
    }
    foreach_in_collection Port [all_outputs] {
        if {[get_object_name $Port] ni {inspect_core_clk core_csr_clk}} {
            set_output_delay -clock CoreClock -max 1.000 $Port
            set_output_delay -clock CoreClock -min -0.100 $Port
        }
        set_load 0.035 $Port
    }
    if {[sizeof_collection [all_clocks]]!=1} {error "Unexpected additional clocks"}
    foreach {Port Name} {inspect_core_clk InspectCoreClock core_csr_clk CoreCsrClock} {
        set Pin [get_ports -quiet $Port]
        if {[sizeof_collection $Pin]!=1} {error "Missing forwarded clock output $Port"}
        set Starts [lsort [get_object_name [all_fanin -flat -startpoints_only -to $Pin]]]
        if {$Starts ne "clk"} {error "Clock output $Port is not solely forwarded clk"}
        create_generated_clock -name $Name -source [get_ports clk] -divide_by 1 -combinational $Pin
        set_clock_uncertainty -setup 0.200 [get_clocks $Name]
        set_clock_uncertainty -hold 0.100 [get_clocks $Name]
        set_clock_transition 0.100 [get_clocks $Name]
    }
    if {[sizeof_collection [all_clocks]]!=3} {error "Expected root plus two forwarded output clocks"}
    source [file join $Tools AsicCommon.tcl]
    write_sdc -nosplit before_compile.sdc
    set BudgetSignature [FrozenBudgetSignature before_compile.sdc]
    puts "SYSTEM_STAGE: compile_start"
    if {![compile_ultra -no_autoungroup -no_boundary_optimization]} {error "System compile failed"}
    write -hierarchy -format ddc -output baseline.ddc
    write -hierarchy -format verilog -output baseline.v
    write_sdc -nosplit baseline.sdc
    puts "SYSTEM_STAGE: baseline_saved"
    set BeforeSetup [PathSlack max]
    set BeforeHold [PathSlack min]
    set Repaired 0
    if {$BeforeHold<0} {
        puts "SYSTEM_STAGE: one_hold_attempt"
        set_fix_hold [all_clocks]
        if {![compile -incremental_mapping -only_hold_time]} {error "System hold-only compile failed"}
        set Repaired 1
    }
    write -hierarchy -format ddc -output candidate.ddc
    write -hierarchy -format verilog -output candidate.v
    write_sdc -nosplit candidate.sdc
    puts "SYSTEM_STAGE: candidate_saved"
    if {$BudgetSignature ne [FrozenBudgetSignature candidate.sdc]} {error "System timing requirements changed"}
    CheckMacroCounts
    set After [FrozenAccelerator]
    if {[dict size $Frozen]!=[dict size $After]} {error "Frozen accelerator leaf count changed"}
    dict for {Name Ref} $Frozen {
        if {![dict exists $After $Name] || [dict get $After $Name] ne $Ref} {
            error "Frozen accelerator changed: $Name"
        }
    }
    set Setup [PathSlack max]
    set Hold [PathSlack min]
    source [file join $Tools AreaBreakdown.tcl]
    WriteAreaBreakdown $Out
    report_clock > clocks.rpt
    report_area -hierarchy > area.rpt
    report_reference -hierarchy > references.rpt
    report_units > units.rpt
    report_qor > qor.rpt
    check_design > check_design.rpt
    check_timing > check_timing.rpt
    report_constraint -all_violators > constraint_violations.rpt
    report_timing -delay_type max -max_paths 20 -significant_digits 6 > setup.rpt
    report_timing -delay_type min -max_paths 20 -significant_digits 6 > hold.rpt
    saif_map -write_map system_name_map.tcl
    foreach Command {read_saif report_saif saif_map} {
        redirect [file join $Out ${Command}_help.txt] {help $Command}
        if {[llength [info commands man]]} {
            catch {redirect [file join $Out ${Command}_manual.txt] {man $Command}}
        }
    }
    set F [open summary.txt w]
    foreach {Key Value} [list TOP e203_cpu_top SOURCE_ID 707cd7f4a0a4d416d11bac71112980079e0a9d34 PERIOD_NS 6.666667 \
        BOUNDARY "E203 CPU+internal ICB+frozen NICE/TPU+112KiB private SRAM+512KiB shared TCM; external peripherals excluded" \
        PRIVATE_SRAM_COUNT 56 SHARED_SRAM_COUNT 64 SHARED_CAPACITY_BYTES 524288 \
        FROZEN_ACCELERATOR_LEAVES [dict size $Frozen] FROZEN_ACCELERATOR UNCHANGED \
        BASELINE_SETUP_WNS_NS $BeforeSetup BASELINE_HOLD_WNS_NS $BeforeHold \
        HOLD_REPAIR_ATTEMPTED $Repaired SETUP_WNS_NS $Setup HOLD_WNS_NS $Hold \
        SETUP_STATUS [expr {$Setup>=0 ? "PASS" : "FAIL"}] HOLD_STATUS [expr {$Hold>=0 ? "PASS" : "FAIL"}] \
        SYSTEM_LIBRARY_AREA_UM2 [LibraryLeafArea] \
        POWER_STATUS "PENDING_SYSTEM_ACTIVITY; no vectorless power claimed" \
        FUNCTION_STATUS "PENDING_FULL_CPU_WITH_MACRO_TCM_EQUIVALENCE" \
        ACCEPTANCE "mapped reports only; inspect timing/check reports; no full-system acceptance"] {
        puts $F "$Key: $Value"
    }
    close $F
    set_svf -off
    puts "SYSTEM_MAPPING_REPORTS_COMPLETE: $Out"
} Why]} {
    puts stderr "SYSTEM_MAPPING_ERROR: $Why"
    puts stderr $::errorInfo
    exit 1
}
exit 0
