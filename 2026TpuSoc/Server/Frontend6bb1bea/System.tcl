# New system mapping with the already accepted accelerator frozen.
if {[catch {
source Config.tcl
set target_library [list $StdDb]
set link_library [concat [list *] $target_library $SramDbs]
set search_path [concat $search_path $Includes]
set_host_options -max_cores 4
source $Common
saif_map -start
read_ddc $AcceleratorDdc
current_design SubmissionAccelerator
set FrozenArea [LibraryLeafArea]
set_dont_touch [get_designs SubmissionAccelerator] true
define_design_lib WORK -path ./work
analyze -format sverilog -define {SYNTHESIS TPU_MATRIX_ROWS=2} $Sources
elaborate SystemPhysical
current_design SystemPhysical
if {![link]} {error "System link failed"}
set FrozenCell [get_cells Backend/Accelerator]
if {[sizeof_collection $FrozenCell]!=1} {error "Missing frozen accelerator instance"}
set_dont_touch $FrozenCell true
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}]
set_dont_touch $Macros true
source $Constraints
check_design
puts "SYSTEM_STAGE: compile current CPU/bus/physical endpoints; accelerator frozen"
flush stdout
compile_ultra -no_autoungroup -no_boundary_optimization
write -format ddc -hierarchy -output baseline.ddc
redirect setup_before_hold.rpt {report_timing -delay_type max -max_paths 5}
redirect hold_before_hold.rpt {report_timing -delay_type min -max_paths 5}
if {[PathSlack min]<0 && [PathSlack max]>=0} {
    set_fix_hold [get_clocks CoreClock]
    compile -incremental_mapping -only_hold_time
}
change_names -rules verilog -hierarchy
write -format ddc -hierarchy -output candidate.ddc
write -format verilog -hierarchy -output candidate.v
write_sdc candidate.sdc
redirect area.rpt {report_area -hierarchy}
redirect design.rpt {report_design}
redirect setup.rpt {report_timing -delay_type max -max_paths 20 -significant_digits 6}
redirect hold.rpt {report_timing -delay_type min -max_paths 20 -significant_digits 6}
redirect check_timing.rpt {check_timing}
redirect violations.rpt {report_constraint -all_violators}
foreach {Ref Count} {RAMSP1024X16 56 RAMSP4096X16 80} {
    if {[sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]!=$Count} {error "Wrong system macro count: $Ref"}
}
set F [open cells.tsv w]
foreach_in_collection C [get_cells -hierarchical -filter {is_hierarchical == false}] {
    puts $F "[get_object_name $C]\t[get_attribute $C ref_name]"
}
close $F
current_instance Backend/Accelerator
set After [LibraryLeafArea]
current_instance
if {abs($After-$FrozenArea)>0.01} {error "Frozen accelerator area changed"}
set F [open Metrics.tsv w]
puts $F "source_commit\t6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6"
puts $F "accelerator_area_um2\t$After"
puts $F "system_area_um2\t[LibraryLeafArea]"
puts $F "setup_wns_ns\t[PathSlack max]"
puts $F "hold_wns_ns\t[PathSlack min]"
close $F
puts "NEW_6BB1BEA_SYSTEM_MAPPED"
} Why]} {puts stderr "SYSTEM_ERROR: $Why"; puts stderr $::errorInfo; exit 2}
exit 0
