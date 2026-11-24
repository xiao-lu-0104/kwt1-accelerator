# Only the current pinned 707cd7f system netlist and SDC are imported as a design.
source [file join [file dirname [info script]] PrCommon.tcl]
proc CurrentSignature {} {
    set R [dict create]
    foreach_in_collection C [get_cells -hierarchical -filter {is_hierarchical == false}] {
        dict set R [get_object_name $C] [get_attribute $C ref_name]
    }
    return $R
}
if {[catch {
    source CurrentConfig.tcl
    PrRecord SCOPE NEW_707CD7F_E203_CPU_TOP_PRIVATE56_SHARED64
    PrRecord LIMITATIONS INITIAL_GEOMETRIC_PLACEMENT_NO_RC_PG_STRAPS_CTS_ROUTE_SIGNOFF
    foreach {Name Options} {
        create_lib {-technology -ref_libs} read_verilog {-top} link_block {}
        create_mode {} create_corner {} create_scenario {-name -mode -corner}
        current_scenario {} read_sdc {} initialize_floorplan {-core_utilization -core_offset}
        create_net {-power -ground} connect_pg_net {-net} get_pins {-physical_context}
        create_placement {-floorplan -effort} report_placement {-hard_macro_overlap}
        set_host_options {-max_cores} save_block {} save_lib {} write_def {}
    } {PrNeed $Name $Options}
    if {[file exists $PrDesignLib]} {error "Refusing existing current design library"}
    PrStep create_lib [list create_lib $PrDesignLib -technology $PrTechnology -ref_libs $PrRefLibs]
    PrStep read_current_verilog [list read_verilog -top e203_cpu_top $PrNetlist]
    PrStep link_current [list link_block] 1
    set Unbound [sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]
    PrRecord UNBOUND_CELLS $Unbound
    if {$Unbound!=0} {error "New system has unresolved physical instances"}
    foreach {Ref Count} {RAMSP1024X16 56 RAMSP4096X16 64} {
        set Actual [sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]
        PrRecord MACRO_COUNT "$Ref $Actual"
        if {$Actual!=$Count} {error "Current system SRAM count mismatch"}
    }
    set Before [CurrentSignature]
    if {[dict size $Before]<100000} {error "Unexpectedly small new system import"}
    PrRecord LEAF_CELLS [dict size $Before]
    PrStep create_mode [list create_mode FUNC]
    PrStep create_corner [list create_corner INITIAL]
    PrStep create_scenario [list create_scenario -name FUNC_INITIAL -mode FUNC -corner INITIAL]
    PrStep current_scenario [list current_scenario FUNC_INITIAL]
    PrStep read_current_sdc [list read_sdc $PrSdc]
    PrReport report_clocks
    PrReport report_units
    set CoreClocks [get_clocks -quiet CoreClock]
    PrRecord CORE_CLOCK_COUNT [sizeof_collection $CoreClocks]
    if {[sizeof_collection $CoreClocks]!=1} {error "Expected exactly one CoreClock after current SDC import"}
    set ActualPeriod [get_attribute $CoreClocks period]
    PrRecord CORE_CLOCK_PERIOD_NATIVE $ActualPeriod
    PrRecord CORE_CLOCK_CHECK_EXPECTED $PrExpectedClockPeriod
    if {abs($ActualPeriod-$PrExpectedClockPeriod)>0.000000001} {
        error "Imported CoreClock differs from the validated serialized SDC period"
    }
    PrStep create_power [list create_net -power VDD]
    PrStep create_ground [list create_net -ground VSS]
    foreach {Net Names} [list VDD $PrPowerPins VSS $PrGroundPins] {
        foreach Pin $Names {
            set Pins [get_pins -physical_context "*/$Pin"]
            if {[sizeof_collection $Pins]==0} {error "Missing reviewed PG pins $Pin"}
            PrStep connect_pg [list connect_pg_net -net $Net $Pins]
        }
    }
    PrRecord PG_STATUS LOGICAL_CONNECTIONS_ONLY
    PrStep floorplan [list initialize_floorplan -core_utilization 0.45 -core_offset {25 25 25 25}]
    PrStep save_imported_block [list save_block]
    PrStep save_imported_library [list save_lib]
    PrStep write_initial_def [list write_def initial_floorplan.def]
    PrStep host_options [list set_host_options -max_cores 4]
    PrStep initial_placement [list create_placement -floorplan -effort low]
    set After [CurrentSignature]
    if {[dict size $Before]!=[dict size $After]} {error "Initial placement changed leaf count"}
    dict for {Name Ref} $Before {
        if {![dict exists $After $Name] || [dict get $After $Name] ne $Ref} {error "Initial placement changed cell $Name"}
    }
    PrStep save_placed_block [list save_block]
    PrStep save_placed_library [list save_lib]
    PrStep write_placed_def [list write_def placed_707cd7f.def]
    source [file join [file dirname [info script]] RegularIo.tcl]
    # IO changes physical terminals only; retain the exact logical leaf mapping.
    set IoAfter [CurrentSignature]
    if {[dict size $Before]!=[dict size $IoAfter]} {error "IO placement changed leaves"}
    dict for {Name Ref} $Before {
        if {![dict exists $IoAfter $Name] || [dict get $IoAfter $Name] ne $Ref} {error "IO changed leaf $Name"}
    }
    PrReport report_placement -hard_macro_overlap
    PrReport report_units
    PrReport report_design
    PrReport report_clocks
    PrReport report_design_mismatch
    set F [open core_bbox.txt w]
    puts $F [get_attribute [current_block] core_area_bbox]
    close $F
    set F [open macros.tsv w]
    puts $F "instance\tref\tx1\ty1\tx2\ty2"
    foreach_in_collection C [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}] {
        set B [get_attribute $C bbox]
        if {[llength $B]!=2 || [llength [lindex $B 0]]!=2 || [llength [lindex $B 1]]!=2} {error "Unexpected native macro bbox"}
        puts $F "[get_object_name $C]\t[get_attribute $C ref_name]\t[join [concat [lindex $B 0] [lindex $B 1]] \t]"
    }
    close $F
    PrRecord LOGICAL_LEAF_SIGNATURE UNCHANGED
    PrRecord RESULT NEW_SYSTEM_INITIAL_PLACEMENT_NATIVE_COMPLETE
} Why]} {
    PrRecord ERROR $Why
    puts stderr $::errorInfo
    PrRecord RESULT NEW_SYSTEM_INITIAL_PLACEMENT_INCOMPLETE
    exit 2
}
exit 0
