# Probe installed APIs and physical state on a copy of the successful 1109 block.
source [file join [file dirname [info script]] PrCommon.tcl]
proc ProbeAttributes {Class} {
    redirect "${Class}_attributes.rpt" [list list_attributes -application -class $Class]
    set F [open "${Class}_attributes.rpt" r];set Text [read $F];close $F
    return $Text
}
proc HasAttribute {Text Name} {return [regexp "\\m${Name}\\M" $Text]}
if {[catch {
    source BackendProbeConfig.tcl
    foreach {N O} {open_lib {} set_ref_libs {-ref_libs} open_block {} link_block {} list_attributes {-application -class}} {PrNeed $N $O}
    PrStep open_copy [list open_lib $PrDesignLib]
    PrStep copied_references [list set_ref_libs -ref_libs $PrRefLibs]
    PrStep open_1109 [list open_block e203_cpu_top]
    PrStep link_copy [list link_block] 1
    set U [sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]
    if {$U!=0} {error "Unbound objects in the successful-layout copy"}
    set F [open BackendOverview.txt w]
    puts $F "TOP: [get_object_name [current_block]]"
    puts $F "UNBOUND: $U"
    puts $F "LEAVES: [sizeof_collection [get_cells -hierarchical -filter {is_hierarchical == false}]]"
    foreach {Ref Expected} {RAMSP1024X16 56 RAMSP4096X16 64} {
        set N [sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]
        puts $F "MACROS: $Ref $N"
        if {$N!=$Expected} {error "Current system macro inventory changed"}
    }
    puts $F "CORE_BBOX: [get_attribute [current_block] core_area_bbox]"
    set Attributes [ProbeAttributes cell]
    foreach Name {physical_status placement_status is_placed is_fixed} {
        if {[HasAttribute $Attributes $Name]} {
            set Counts [dict create]
            foreach Value [get_attribute [get_cells -hierarchical -filter {is_hierarchical == false}] $Name] {dict incr Counts $Value}
            puts $F "LEAF_STATUS: $Name $Counts"
        }
    }
    set Attributes [ProbeAttributes layer]
    puts $F "LAYERS: name and available native attributes"
    foreach_in_collection L [get_layers *] {
        set Data [list [get_object_name $L]]
        foreach A {layer_type routing_direction preferred_direction pitch min_width min_spacing track_offset} {
            if {[HasAttribute $Attributes $A]} {lappend Data $A [get_attribute $L $A]}
        }
        puts $F $Data
    }
    puts $F "CLOCKS:"
    foreach_in_collection C [all_clocks] {puts $F "[get_object_name $C] period=[get_attribute $C period]"}
    close $F
    PrReport report_units
    PrReport report_placement -hard_macro_overlap
    PrReport report_design
    PrReport report_clocks
    set S [open BackendSyntax.txt w]
    set K [open BackendKeySyntax.txt w]
    set Available {}; set Missing {}
    foreach Name {
        read_parasitic_tech set_parasitic_parameters report_parasitic_parameters check_parasitic_tech
        set_ignored_layers create_pg_ring_pattern create_pg_mesh_pattern create_pg_std_cell_conn_pattern
        create_pg_macro_conn_pattern set_pg_strategy set_pg_strategy_via_rule set_pg_via_master_rule
        compile_pg check_pg_connectivity check_pg_drc connect_pg_net create_port create_terminal
        set_fixed_objects set_block_pin_constraints place_pins legalize_placement check_legality
        place_opt clock_opt route_auto route_opt check_routes report_qor report_timing report_constraints
        write_verilog write_def write_gds write_sdc write_parasitics write_sdf
        set_clock_tree_options set_lib_cell_purpose set_app_options set_scenario_status
    } {
        if {![llength [info commands $Name]]} {puts $S "UNAVAILABLE: $Name";lappend Missing $Name;continue}
        lappend Available $Name
        redirect "${Name}_manual.txt" [list man $Name]
        set F [open "${Name}_manual.txt" r];set M [read $F];close $F
        while {[string first "\b" $M]>=0} {if {![regsub -all ".\b" $M {} M]} {break}}
        set P [string first SYNTAX $M]
        puts $S "COMMAND: $Name"
        if {$P<0} {puts $S "SYNTAX_SECTION_NOT_FOUND";continue}
        set Section [string range $M $P end]
        set End [string first DESCRIPTION $Section]
        if {$End>0} {set Section [string range $Section 0 [expr {$End-1}]]}
        # Full native manual is retained even when the console synopsis is short.
        puts $S [string range $Section 0 1600]
        if {$Name in {read_parasitic_tech set_parasitic_parameters create_pg_ring_pattern create_pg_mesh_pattern set_pg_strategy}} {
            puts $K "COMMAND: $Name"
            puts $K [string range $Section 0 1100]
        }
    }
    puts $K "AVAILABLE_COMMANDS: $Available"
    puts $K "MISSING_COMMANDS: $Missing"
    close $S
    close $K
    PrRecord RESULT BACKEND_PROBE_NATIVE_COMPLETE
} Why]} {
    PrRecord ERROR $Why
    puts stderr $::errorInfo
    exit 2
}
exit 0
