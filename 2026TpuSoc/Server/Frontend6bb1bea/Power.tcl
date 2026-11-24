# Report only: same system DDC and current cold-task activity.
if {[catch {
source Config.tcl
set target_library [list $StdDb]
set link_library [concat [list *] $target_library $SramDbs]
saif_map -start
read_ddc $SystemDdc
current_design SystemPhysical
if {![link]} {error "Power system link failed"}
reset_switching_activity -all
redirect read_saif_manual.txt {man read_saif}
if {[read_saif -input $ActivityFile -instance_name PowerTest/Dut -auto_map_names] eq "0"} {error "SAIF annotation failed"}
redirect power.rpt {report_power}
redirect design.rpt {report_design}
redirect power_hierarchy.rpt {report_power -hierarchy}
redirect saif_hierarchy.rpt {report_saif -hierarchy}
redirect saif_missing.rpt {report_saif -hierarchy -missing}
redirect units.rpt {report_units}
set Keys {ACCELERATOR CPU_BUS SHARED_SRAM TCM OTHER}
foreach Key $Keys {set Group($Key) ""}
foreach_in_collection C [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set N [get_object_name $C]
    set Ref [get_attribute $C ref_name]
    if {$Ref in {**logic_0** **logic_1**}} {continue}
    if {[string match Backend/Accelerator/* $N]} {set Key ACCELERATOR
    } elseif {[string match Shared/* $N]} {set Key SHARED_SRAM
    } elseif {[string match Itcm/* $N] || [string match Dtcm/* $N]} {set Key TCM
    } elseif {[string match Backend/* $N]} {set Key CPU_BUS
    } else {set Key OTHER}
    set Group($Key) [add_to_collection $Group($Key) $C]
}
set F [open groups.tsv w]
foreach Key $Keys {
    set Count [sizeof_collection $Group($Key)]
    puts $F "$Key\t$Count"
    if {$Count>0} {redirect "${Key}_power.rpt" {report_power -cell -only $Group($Key) -nworst $Count -nosplit}}
}
close $F
foreach {Name Scope} {accelerator Backend/Accelerator cpu Backend/Cpu bus Backend/SystemBus shared Shared itcm Itcm dtcm Dtcm} {
    set C [get_cells -quiet $Scope]
    if {[sizeof_collection $C]!=1} {error "Missing activity region $Scope"}
    redirect "${Name}_coverage.rpt" {report_saif -hierarchy -only $C}
}
puts "NEW_6BB1BEA_POWER_REPORTS_COMPLETE"
} Why]} {puts stderr "POWER_ERROR: $Why";puts stderr $::errorInfo;exit 2}
exit 0
