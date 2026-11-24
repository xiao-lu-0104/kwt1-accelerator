# Full SoC activity, same current DDC. No compile or vectorless substitution.
if {[catch {
source Config.tcl
set target_library [list $StdDb]
set link_library [concat [list *] $target_library $SramDbs]
saif_map -start
read_ddc $CurrentDdc
current_design $Top
if {![link]} {error "Current power DDC link failed"}
redirect read_saif_manual.txt {man read_saif}
set F [open read_saif_manual.txt r];set M [read $F];close $F
if {[string first -auto_map_names $M]<0} {error "Installed read_saif options require review"}
reset_switching_activity -all
if {[read_saif -input $ActivityFile -instance_name $ActivityInstance -auto_map_names] eq "0"} {error "Activity read failed"}
redirect power.rpt {report_power}
redirect power_hierarchy.rpt {report_power -hierarchy}
redirect saif_hierarchy.rpt {report_saif -hierarchy}
redirect saif_missing.rpt {report_saif -hierarchy -missing}
redirect units.rpt {report_units}
set A [get_cells -quiet $AcceleratorScope]
if {[sizeof_collection $A]!=1} {error "Bind actual accelerator power scope"}
set Leaves [get_cells -hierarchical -filter "is_hierarchical == false && full_name =~ $AcceleratorScope/*"]
set Count [sizeof_collection $Leaves]
if {$Count==0} {error "Empty accelerator leaf collection"}
redirect accelerator_power.rpt {report_power -cell -only $Leaves -nworst $Count -nosplit}
set F [open AcceleratorCount.txt w];puts $F $Count;close $F
redirect accelerator_coverage.rpt {report_saif -hierarchy -only $A}
set F [open Status.txt w]
puts $F "SOURCE_COMMIT: $SourceCommit"
puts $F "ESTIMATE: TT prelayout, full system and accelerator separately"
puts $F "ACCEPTANCE: review hierarchy default/propagated/X and all SRAM models; top-only coverage is insufficient"
close $F
puts "POWER_REPORTS_COMPLETE"
} Why]} {puts stderr "POWER_ERROR: $Why";puts stderr $::errorInfo;exit 2}
exit 0
