# Report-only view: model two clock outputs as clocks, preserving all data budgets.
proc LeafSignature {} {
    set Result [dict create]
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        dict set Result [get_object_name $Cell] [get_attribute $Cell ref_name]
    }
    return $Result
}
if {[catch {
    set Out $::env(TPU_CLOCK_OUT)
    set Tools $::env(TPU_CLOCK_TOOLS)
    cd $Out
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB) $::env(TPU_SYSTEM_DB)]]
    # read_ddc returns a design list, not a boolean status.
    read_ddc $::env(TPU_CLOCK_DDC)
    if {[sizeof_collection [get_designs -quiet e203_cpu_top]]!=1} {error "Cannot load original system checkpoint top"}
    current_design e203_cpu_top
    if {![link]} {error "Cannot link original system checkpoint"}
    source [file join $Tools AsicCommon.tcl]
    source [file join $Tools AreaBreakdown.tcl]
    WriteAreaBreakdown $Out
    if {[sizeof_collection [all_clocks]]!=1 || [sizeof_collection [get_clocks -quiet CoreClock]]!=1} {
        error "Expected original single CoreClock"
    }
    if {abs([get_attribute [get_clocks CoreClock] period]-6.666667)>0.000001} {error "Unexpected clock period"}
    foreach {Ref Expected} {RAMSP1024X16 56 RAMSP4096X16 64} {
        if {[sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]!=$Expected} {error "Wrong memory inventory"}
    }
    set Before [LeafSignature]
    set BeforeSetup [PathSlack max]
    set BeforeHold [PathSlack min]
    write_sdc -nosplit loaded.sdc
    report_timing -delay_type min -max_paths 3 -significant_digits 9 > original_hold.rpt
    set SourceEvidence {}
    foreach Port {inspect_core_clk core_csr_clk} {
        set Pin [get_ports -quiet $Port]
        if {[sizeof_collection $Pin]!=1} {error "Missing clock output $Port"}
        set Starts [all_fanin -flat -startpoints_only -to $Pin]
        set StartNames [lsort [get_object_name $Starts]]
        lappend SourceEvidence "$Port: $StartNames"
        if {$StartNames ne "clk"} {error "Clock output $Port is not a pure forwarded clk"}
    }
    foreach {Port Name} {inspect_core_clk InspectCoreClock core_csr_clk CoreCsrClock} {
        set Pin [get_ports -quiet $Port]
        # These are clock outputs; external DATA launch/capture delay is inapplicable.
        # Keep the original loads. No false path, min/max exception or data budget change.
        remove_output_delay $Pin
        create_generated_clock -name $Name -source [get_ports clk] -divide_by 1 -combinational $Pin
        set_clock_uncertainty -setup 0.200 [get_clocks $Name]
        set_clock_uncertainty -hold 0.100 [get_clocks $Name]
        set_clock_transition 0.100 [get_clocks $Name]
    }
    set F [open clock_port_sources.txt w]
    foreach Line $SourceEvidence {puts $F $Line}
    close $F
    if {[sizeof_collection [all_clocks]]!=3} {error "Expected root clock and two forwarded output clocks"}
    set After [LeafSignature]
    if {[dict size $Before]!=[dict size $After]} {error "Leaf count changed"}
    dict for {Name Ref} $Before {
        if {![dict exists $After $Name] || [dict get $After $Name] ne $Ref} {error "Leaf changed: $Name"}
    }
    set Setup [PathSlack max]
    set Hold [PathSlack min]
    write_sdc -nosplit clock_ports_corrected.sdc
    report_clock > clocks.rpt
    report_port -verbose [get_ports {inspect_core_clk core_csr_clk}] > clock_ports.rpt
    check_timing > check_timing.rpt
    check_design > check_design.rpt
    report_constraint -all_violators > constraint_violations.rpt
    report_timing -delay_type max -max_paths 20 -significant_digits 9 > setup.rpt
    report_timing -delay_type min -max_paths 20 -significant_digits 9 > hold.rpt
    set F [open summary.txt w]
    foreach {Key Value} [list MODE REPORT_ONLY_CLOCK_PORT_CONSTRAINT_CORRECTION \
        TOP e203_cpu_top NETLIST UNCHANGED ORIGINAL_SETUP_WNS_NS $BeforeSetup ORIGINAL_HOLD_WNS_NS $BeforeHold \
        SETUP_WNS_NS $Setup HOLD_WNS_NS $Hold \
        SETUP_STATUS [expr {$Setup>=0 ? "PASS" : "FAIL"}] HOLD_STATUS [expr {$Hold>=0 ? "PASS" : "FAIL"}] \
        DATA_BUDGETS_STATUS PENDING_SDC_DIFF_VERIFICATION \
        CLOCK_OUTPUTS "inspect_core_clk core_csr_clk; divide-by-1 generated from CoreClock; original loads retained" \
        ACCEPTANCE "TT ideal-clock report only; no CTS/routing/corner signoff; system function/power pending"] {
        puts $F "$Key: $Value"
    }
    close $F
    puts "CLOCK_PORT_REPORT_COMPLETE: $Out"
} Why]} {
    puts stderr "CLOCK_PORT_REPORT_ERROR: $Why"
    puts stderr $::errorInfo
    exit 1
}
exit 0
