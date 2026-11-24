# Read-only annotated estimate; never optimize, change constraints or save DDC.
proc OptionalTaskReport {Path Body} {
    if {[catch {uplevel 1 [list redirect $Path $Body]} Why]} {
        set F [open ${Path}.error.txt w]; puts $F "$Why\n$::errorInfo"; close $F
        puts "OPTIONAL_TASK_REPORT_UNAVAILABLE: $Path"
    }
}
if {[catch {
    cd $::env(TPU_TASK_CASE)
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
    read_ddc $::env(TPU_POWER_DDC)
    current_design e203_subsys_nice_core
    if {![link]} {error "Frozen candidate link failed"}
    set Clocks [all_clocks]
    if {[sizeof_collection $Clocks]!=1 || abs([get_attribute $Clocks period]-6.666667)>0.000001} {
        error "Original single-clock constraints changed"
    }
    set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
    if {[sizeof_collection $Macros]!=56} {error "Private SRAM count changed"}
    foreach Command {reset_switching_activity read_saif report_saif report_power} {
        if {![llength [info commands $Command]]} {error "Required installed command missing: $Command"}
    }
    reset_switching_activity -all
    set Annotated [read_saif -input $::env(TPU_TASK_SAIF) -instance_name SharedTest/Cpu/u_e203_cpu/u_e203_nice_core -verbose]
    if {$Annotated eq "0"} {error "SAIF annotation returned failure"}
    redirect saif_coverage.rpt {report_saif}
    OptionalTaskReport saif_hierarchy.rpt {report_saif -hierarchy}
    OptionalTaskReport saif_missing.rpt {report_saif -hierarchy -missing}
    redirect power.rpt {report_power}
    OptionalTaskReport power_hierarchy.rpt {report_power -hierarchy}
    # Do not hide a failure to account for private memory.
    redirect private_sram_power.rpt {report_power -cell -only $Macros -nworst 56 -nosplit}
    OptionalTaskReport switching_activity.rpt {report_switching_activity}
    redirect units.rpt {report_units}
    puts "TASK_POWER_DDC_COMPLETE: annotated candidate estimate; private_SRAM=56; coverage and unknowns require review"
} Why]} {
    puts stderr "TASK_POWER_ERROR: $Why"
    puts stderr $::errorInfo
    exit 1
}
exit 0
