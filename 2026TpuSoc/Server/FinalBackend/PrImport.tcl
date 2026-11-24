source [file join [file dirname [info script]] PrCommon.tcl]
if {[catch {
    source PrImportConfig.tcl
    PrRecord SCOPE FROZEN_ACCELERATOR_WITH_56_PRIVATE_SRAM_MACROS
    PrRecord RC_STATUS NOT_CONFIGURED_NO_TIMING_SIGNOFF
    PrRecord PLACEMENT_ROUTING NOT_RUN
    foreach {name options} {
        create_lib {-technology -ref_libs}
        read_verilog {-top}
        link_block {}
        get_cells {-hierarchical -filter}
        create_mode {}
        create_corner {}
        create_scenario {-name -mode -corner}
        current_scenario {}
        read_sdc {}
        create_net {-power -ground}
        get_pins {-physical_context}
        connect_pg_net {-net}
        initialize_floorplan {-core_utilization -core_offset}
        save_block {}
        save_lib {}
        write_def {}
    } {PrNeed $name $options}
    if {[file exists $PrDesignLib]} {error "Refusing existing design library"}
    PrStep create_lib [list create_lib $PrDesignLib -technology $PrTechnology -ref_libs $PrRefLibs]
    PrStep read_verilog [list read_verilog -top $PrTop $PrNetlist]
    PrStep link_block [list link_block] 1
    set unbound [sizeof_collection [get_cells -hierarchical -filter {is_unbound == true}]]
    PrRecord UNBOUND_CELLS $unbound
    if {$unbound != 0} {error "Unbound instances remain after linking"}
    set leaves [sizeof_collection [get_cells -hierarchical -filter {is_hierarchical == false}]]
    PrRecord LEAF_CELLS $leaves
    if {$leaves < 1000} {error "Unexpectedly small accelerator import"}
    set macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
    set count [sizeof_collection $macros]
    PrRecord PRIVATE_MACROS $count
    if {$count != 56} {error "Expected exactly 56 private SRAM macros"}
    PrReport report_design_mismatch
    PrStep create_mode [list create_mode FUNC]
    PrStep create_corner [list create_corner INITIAL]
    PrStep create_scenario [list create_scenario -name FUNC_INITIAL -mode FUNC -corner INITIAL]
    PrStep current_scenario [list current_scenario FUNC_INITIAL]
    PrStep read_sdc [list read_sdc $PrSdc]
    PrStep create_power_net [list create_net -power VDD]
    PrStep create_ground_net [list create_net -ground VSS]
    foreach {net names} [list VDD $PrPowerPins VSS $PrGroundPins] {
        foreach pin $names {
            set pins [get_pins -physical_context "*/$pin"]
            set count [sizeof_collection $pins]
            PrRecord PG_PIN_COUNT "$pin $count"
            if {$count == 0} {error "No physical PG pins found for reviewed pin $pin"}
            PrStep connect_pg_net [list connect_pg_net -net $net $pins]
        }
    }
    PrRecord PG_STATUS LOGICAL_CONNECTIONS_ONLY_NO_RINGS_OR_STRAPS
    PrStep initialize_floorplan [list initialize_floorplan -core_utilization 0.55 -core_offset {20 20 20 20}]
    PrStep save_block [list save_block]
    PrStep save_lib [list save_lib]
    PrStep write_def [list write_def $PrDef]
    if {![file isfile $PrDef] || [file size $PrDef] == 0} {error "Initial floorplan DEF missing"}
    PrReport report_design
    PrReport report_units
    PrRecord DESIGN_CHECKS STAGE_SPECIFIC_PHYSICAL_CHECKS_PENDING
    PrRecord RESULT ICC2_IMPORT_AND_INITIAL_FLOORPLAN_COMPLETE_REVIEW_PENDING
} why]} {
    PrRecord ERROR $why
    puts stderr $::errorInfo
    PrReport report_design_mismatch
    PrRecord RESULT ICC2_IMPORT_OR_FLOORPLAN_FAILED
    exit 2
}
exit 0
