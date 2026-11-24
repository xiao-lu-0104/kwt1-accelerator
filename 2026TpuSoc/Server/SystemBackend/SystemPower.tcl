# Read-only pre-layout estimate from full CPU-scope task SAIF. No optimization.
proc PowerLeafSignature {} {
    set Result [dict create]
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        dict set Result [get_object_name $Cell] [get_attribute $Cell ref_name]
    }
    return $Result
}
proc OptionalPowerReport {Path Body} {
    if {[catch {uplevel 1 [list redirect $Path $Body]} Why]} {
        set F [open ${Path}.error.txt w]; puts $F "$Why\n$::errorInfo"; close $F
        puts "OPTIONAL_SYSTEM_POWER_REPORT_UNAVAILABLE: $Path"
    }
}
if {[catch {
    cd $::env(TPU_SYSTEM_POWER_CASE)
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB) $::env(TPU_SYSTEM_DB)]]
    # BEGIN_SAIF_MAPPING_LIFECYCLE
    # Mapping must be active while the checkpoint is read, not just at read_saif.
    if {![llength [info commands saif_map]]} {error "Installed saif_map command required"}
    set MappingStart [saif_map -start]
    if {$MappingStart eq "0"} {error "Cannot activate SAIF name mapping"}
    puts "SAIF_MAPPING_ACTIVE_BEFORE_DDC: started"
    # END_SAIF_MAPPING_LIFECYCLE
    read_ddc $::env(TPU_SYSTEM_POWER_DDC)
    if {[sizeof_collection [get_designs -quiet e203_cpu_top]]!=1} {error "Missing original system top"}
    current_design e203_cpu_top
    if {![link]} {error "Original system checkpoint link failed"}
    if {[sizeof_collection [all_clocks]]!=1 || abs([get_attribute [get_clocks CoreClock] period]-6.666667)>0.000001} {
        error "Unexpected original CoreClock constraints"
    }
    set Before [PowerLeafSignature]
    set Private [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
    set Shared [get_cells -hierarchical -filter {ref_name == RAMSP4096X16}]
    if {[sizeof_collection $Private]!=56 || [sizeof_collection $Shared]!=64} {error "Wrong SRAM inventory"}
    set Itcm [filter_collection $Shared {full_name =~ u_e203_srams/u_e203_itcm_ram/*}]
    set Dtcm [filter_collection $Shared {full_name =~ u_e203_srams/u_e203_dtcm_ram/*}]
    if {[sizeof_collection $Itcm]!=32 || [sizeof_collection $Dtcm]!=32} {error "Wrong ITCM/DTCM inventory"}
    # Reapply exactly the independently verified two forwarded-clock roles.
    foreach {Port Name} {inspect_core_clk InspectCoreClock core_csr_clk CoreCsrClock} {
        set Pin [get_ports $Port]
        remove_output_delay $Pin
        create_generated_clock -name $Name -source [get_ports clk] -divide_by 1 -combinational $Pin
        set_clock_uncertainty -setup 0.200 [get_clocks $Name]
        set_clock_uncertainty -hold 0.100 [get_clocks $Name]
        set_clock_transition 0.100 [get_clocks $Name]
    }
    write_sdc -nosplit power_view.sdc
    foreach Command {reset_switching_activity read_saif report_saif report_power get_switching_activity} {
        if {![llength [info commands $Command]]} {error "Installed command missing: $Command"}
    }
    redirect read_saif_help.txt {help read_saif}
    if {[llength [info commands man]]} {OptionalPowerReport read_saif_manual.txt {man read_saif}}
    set H [open read_saif_help.txt r]; set Help [read $H]; close $H
    if {[file exists read_saif_manual.txt]} {
        set H [open read_saif_manual.txt r]; append Help "\n" [read $H]; close $H
    }
    set Arguments [list -input $::env(TPU_SYSTEM_POWER_SAIF) -instance_name SharedTest/Cpu -verbose]
    set MappingMode DIRECT_HIERARCHY_NAME_MATCH
    set ExternalMap RETAINED_NOT_SOURCED_IN_FIRST_ESTIMATE
    reset_switching_activity -all
    if {[info exists ::env(TPU_SYSTEM_NAME_MAP)] && $::env(TPU_SYSTEM_NAME_MAP) ne ""} {
        if {![llength [info commands saif_map]] || ![file isfile $::env(TPU_SYSTEM_NAME_MAP)]} {
            error "Installed saif_map command and original native mapping file required"
        }
        if {[string first "-map_names" $Help]<0} {error "Installed read_saif documentation lacks -map_names"}
        # saif_map -write_map emits native data, even when its filename ends .tcl.
        # Read through the supported mapping command; never source it as Tcl.
        set MapStatus [saif_map -read_map $::env(TPU_SYSTEM_NAME_MAP)]
        if {$MapStatus eq "0"} {error "Native synthesis name map load failed"}
        lappend Arguments -map_names
        set MappingMode NATIVE_SYNTHESIS_MAP_READ_SAIF_MAP_NAMES
        set ExternalMap LOADED_WITH_SAIF_MAP_READ_MAP
        puts "SYSTEM_NAME_MAP_LOADED: $::env(TPU_SYSTEM_NAME_MAP)"
    } elseif {[string first "-auto_map_names" $Help]>=0} {
        lappend Arguments -auto_map_names
        set MappingMode INSTALLED_READ_SAIF_AUTO_MAP_NAMES
    }
    if {[eval read_saif $Arguments] eq "0"} {error "Full-system SAIF annotation failed"}
    redirect saif_coverage_before_power.rpt {report_saif}
    redirect power.rpt {report_power}
    redirect private_sram_power.rpt {report_power -cell -only $Private -nworst 56 -nosplit}
    redirect shared_itcm_power.rpt {report_power -cell -only $Itcm -nworst 32 -nosplit}
    redirect shared_dtcm_power.rpt {report_power -cell -only $Dtcm -nworst 32 -nosplit}
    redirect saif_coverage.rpt {report_saif}
    redirect saif_missing.rpt {report_saif -hierarchy -missing}
    redirect saif_hierarchy.rpt {report_saif -hierarchy}
    foreach {Label Instance} {cpu_core u_e203_cpu/u_e203_core accelerator u_e203_cpu/u_e203_nice_core shared_tcm u_e203_srams} {
        set Scope [get_cells -quiet $Instance]
        if {[sizeof_collection $Scope]==1} {
            OptionalPowerReport saif_${Label}.rpt {report_saif -hierarchy -only $Scope}
        }
    }
    OptionalPowerReport power_hierarchy.rpt {report_power -hierarchy}
    OptionalPowerReport activity.rpt {report_activity}
    redirect units.rpt {report_units}
    OptionalPowerReport root_clock_activity.txt {puts [get_switching_activity [get_ports clk]]}
    set After [PowerLeafSignature]
    if {[dict size $Before]!=[dict size $After]} {error "Power reporting changed leaf count"}
    dict for {Name Ref} $Before {
        if {![dict exists $After $Name] || [dict get $After $Name] ne $Ref} {error "Power reporting changed leaf $Name"}
    }
    set F [open tool_status.txt w]
    puts $F "TOP: e203_cpu_top"
    puts $F "SAIF_SCOPE: SharedTest/Cpu"
    puts $F "MAPPING_MODE: $MappingMode"
    puts $F "NAME_MAPPING_LIFECYCLE: STARTED_BEFORE_DDC"
    puts $F "EXTERNAL_NAME_MAP: $ExternalMap"
    puts $F "NETLIST: UNCHANGED"
    puts $F "PRIVATE_SRAM_COUNT: 56"
    puts $F "ITCM_SRAM_COUNT: 32"
    puts $F "DTCM_SRAM_COUNT: 32"
    puts $F "ACCEPTANCE: PENDING_COVERAGE_X_SRAM_AND_SYSTEM_BOUNDARY_REVIEW"
    close $F
    puts "SYSTEM_POWER_REPORT_COMPLETE: full CPU scope; private56/ITCM32/DTCM32; coverage and X review pending"
} Why]} {
    puts stderr "SYSTEM_POWER_REPORT_ERROR: $Why"
    puts stderr $::errorInfo
    exit 1
}
exit 0
