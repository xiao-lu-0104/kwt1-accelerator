# Current DDC + current validated task SAIF. Report-only, no optimization.
set PowerStarted [clock seconds]
proc PowerMark {Name} {
    puts "POWER_STEP: $Name elapsed_seconds=[expr {[clock seconds]-$::PowerStarted}]"
    flush stdout
}
proc Signature {} {
    set R [dict create]
    foreach_in_collection C [get_cells -hierarchical -filter {is_hierarchical == false}] {
        dict set R [get_object_name $C] [get_attribute $C ref_name]
    }
    return $R
}
if {[catch {
    cd $::env(NEW_POWER_CASE)
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB) $::env(TPU_SYSTEM_DB)]]
    if {[saif_map -start] eq "0"} {error "Cannot activate mapping before DDC import"}
    PowerMark READ_DDC_BEGIN
    read_ddc $::env(NEW_POWER_DDC)
    PowerMark READ_DDC_END
    if {[sizeof_collection [get_designs -quiet e203_cpu_top]]!=1} {error "Current system DDC missing"}
    current_design e203_cpu_top
    if {![link]} {error "Current system link failed"}
    PowerMark LINK_END
    if {[sizeof_collection [all_clocks]]!=3 || abs([get_attribute [get_clocks CoreClock] period]-6.666667)>0.000001} {
        error "Expected current root plus two forwarded clocks"
    }
    foreach Name {CoreCsrClock InspectCoreClock} {
        if {[sizeof_collection [get_clocks -quiet $Name]]!=1} {error "Missing current forwarded clock $Name"}
    }
    source [file join $::env(NEW_POWER_TOOLS) AsicCommon.tcl]
    source [file join $::env(NEW_POWER_TOOLS) AreaBreakdown.tcl]
    set Before [Signature]
    write_sdc -nosplit loaded.sdc
    set Budget [FrozenBudgetSignature loaded.sdc]
    foreach {Ref Count} {RAMSP1024X16 56 RAMSP4096X16 64} {
        if {[sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]!=$Count} {error "Wrong SRAM inventory"}
    }
    redirect read_saif_manual.txt {man read_saif}
    set F [open read_saif_manual.txt r]; set Manual [read $F]; close $F
    if {[string first -auto_map_names $Manual]<0} {error "Installed read_saif manual lacks automatic name matching"}
    PowerMark RESET_ACTIVITY_BEGIN
    reset_switching_activity -all
    PowerMark RESET_ACTIVITY_END
    PowerMark READ_SAIF_BEGIN
    if {[read_saif -input $::env(NEW_POWER_SAIF) -instance_name SharedTest/Cpu -auto_map_names] eq "0"} {
        error "Current full-system task SAIF annotation failed"
    }
    PowerMark READ_SAIF_END
    redirect saif_global.rpt {report_saif}
    PowerMark SYSTEM_POWER_BEGIN
    redirect power.rpt {report_power}
    PowerMark SYSTEM_POWER_END
    redirect saif_hierarchy.rpt {report_saif -hierarchy}
    redirect saif_missing.rpt {report_saif -hierarchy -missing}
    redirect power_hierarchy.rpt {report_power -hierarchy}
    redirect units.rpt {report_units}
    redirect constraints.rpt {report_constraint -all_violators}
    PowerMark GROUP_COLLECTION_BEGIN
    set Keys {ACCELERATOR_LOGIC_AND_INTERFACES ACCELERATOR_PRIVATE_SRAM REUSED_CPU_AND_INTERNAL_ICB_LOGIC SHARED_ITCM_MACROS SHARED_DTCM_MACROS SHARED_TCM_BINDING_LOGIC OTHER_SYSTEM_LOGIC}
    foreach Key $Keys {set Groups($Key) ""}
    foreach_in_collection C [get_cells -hierarchical -filter {is_hierarchical == false}] {
        set Ref [get_attribute $C ref_name]
        if {$Ref in {**logic_0** **logic_1**}} {continue}
        set Key [AreaClass [get_object_name $C] $Ref]
        set Groups($Key) [add_to_collection $Groups($Key) $C]
    }
    set F [open groups.tsv w]
    PowerMark GROUP_COLLECTION_END
    foreach Key $Keys {
        set Count [sizeof_collection $Groups($Key)]
        if {$Count==0} {error "Empty expected power group $Key"}
        puts $F "$Key\t$Count"
        PowerMark "GROUP_POWER_BEGIN $Key"
        redirect "${Key}_power.rpt" {report_power -cell -only $Groups($Key) -nworst $Count -nosplit}
        PowerMark "GROUP_POWER_END $Key"
    }
    close $F
    foreach {Name Instance} {cpu_core u_e203_cpu/u_e203_core accelerator u_e203_cpu/u_e203_nice_core shared_tcm u_e203_srams} {
        set Scope [get_cells -quiet $Instance]
        if {[sizeof_collection $Scope]!=1} {error "Missing activity region $Instance"}
        redirect "${Name}_coverage.rpt" {report_saif -hierarchy -only $Scope}
    }
    set After [Signature]
    if {[dict size $Before]!=[dict size $After]} {error "Power reporting changed leaf count"}
    dict for {Name Ref} $Before {
        if {![dict exists $After $Name] || [dict get $After $Name] ne $Ref} {error "Power reporting changed cell $Name"}
    }
    write_sdc -nosplit power_view.sdc
    if {$Budget ne [FrozenBudgetSignature power_view.sdc]} {error "Power reporting changed timing requirements"}
    set F [open ToolStatus.txt w]
    puts $F "MAPPING: START_BEFORE_DDC_THEN_READ_SAIF_AUTO_MAP_NAMES"
    puts $F "NETLIST: UNCHANGED"
    puts $F "TIMING_BUDGETS: UNCHANGED"
    puts $F "SCOPE: e203_cpu_top; 56 private + 64 shared SRAM; default/X review remains"
    close $F
    puts "CURRENT_TASK_POWER_REPORT_COMPLETE"
} Why]} {
    puts stderr "CURRENT_TASK_POWER_ERROR: $Why"
    puts stderr $::errorInfo
    exit 2
}
exit 0
