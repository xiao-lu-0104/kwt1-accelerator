# Power Compiler syntax: object_list, with no PrimeTime -toggle_rate option.
if {[catch {
    cd $::env(TPU_QUAL_CASE)
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
    read_ddc $::env(TPU_POWER_DDC)
    current_design e203_subsys_nice_core
    if {![link]} {error "Frozen checkpoint link failed"}
    set Clocks [all_clocks]
    if {[sizeof_collection $Clocks]!=1 || abs([get_attribute $Clocks period]-6.666667)>0.000001} {
        error "Original clock constraints changed"
    }
    if {[sizeof_collection [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]]!=56} {
        error "Private SRAM count changed"
    }
    reset_switching_activity -all
    if {[read_saif -input $::env(TPU_QUAL_SAIF) -instance_name SharedTest/Cpu/u_e203_cpu/u_e203_nice_core -verbose] eq "0"} {
        error "Original SAIF annotation failed"
    }
    redirect clock_command_help.txt {help get_switching_activity}
    if {[catch {redirect activity.rpt {report_activity}} ReportError]} {
        set E [open activity.rpt.error.txt w]; puts $E $ReportError; close $E
    }
    set Wanted {nice_clk Bus/Clock Tpu/Clock Tpu/Core/Clock}
    set Found [dict create]
    foreach_in_collection Net [get_nets -hierarchical] {
        set Name [get_object_name $Net]
        if {$Name in $Wanted} {dict set Found $Name $Net}
    }
    set F [open clocks.txt w]
    foreach Name $Wanted {
        if {![dict exists $Found $Name]} {error "Clock alias absent: $Name"}
        set Object [dict get $Found $Name]
        redirect -variable Activity {puts [get_switching_activity $Object]}
        puts $F "$Name\t[string map {\n { } \r { } \t { }} $Activity]"
    }
    close $F
    puts "QUALIFICATION_CLOCK_COMPLETE: four clock aliases queried; no activity override"
} Why]} {
    if {[info exists F]} {catch {close $F}}
    puts stderr "QUALIFICATION_CLOCK_ERROR: $Why"
    puts stderr $::errorInfo
    exit 1
}
exit 0
