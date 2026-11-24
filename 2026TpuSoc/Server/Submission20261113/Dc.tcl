# Generic current-commit synthesis. Source lists and constraints must be bound.
if {[catch {
source Config.tcl
set target_library [list $StdDb]
set link_library [concat [list *] $target_library $SramDbs]
set_host_options -max_cores 4
set_app_var verilogout_no_tri true
set_svf guidance.svf
saif_map -start
set_app_var search_path [concat $search_path $Includes]
source [file join $Tools AsicCommon.tcl]
if {$Mode eq "compile"} {
    if {[info exists AcceleratorDdc]} {read_ddc $AcceleratorDdc}
    define_design_lib WORK -path work
    if {![analyze -format sverilog -define $Defines -library WORK $Sources]} {error "RTL analysis failed"}
    elaborate $Top -library WORK
    current_design $Top
    if {![link]} {error "Link failed"}
    if {[info exists AcceleratorDdc]} {
        set A [get_cells -quiet $AcceleratorScope]
        if {[sizeof_collection $A]!=1 || [get_attribute $A ref_name] ne $FrozenAcceleratorTop} {error "Bind the actual frozen accelerator instance"}
        set_dont_touch $A true
    }
    foreach {Ref Count} $MacroCounts {
        set C [get_cells -hierarchical -filter "ref_name == $Ref"]
        if {[sizeof_collection $C] != $Count} {error "Unexpected macro count: $Ref"}
        set_dont_touch $C true
    }
    source $ConstraintFile
    set Main [get_clocks -quiet CoreClock]
    if {[sizeof_collection $Main]!=1 || abs([get_attribute $Main period]-$ExpectedPeriod)>1e-6} {error "150MHz clock missing"}
    puts "DC_STAGE: compile_start";flush stdout
    if {![compile_ultra -no_autoungroup -no_boundary_optimization]} {error "Compile failed"}
    write -hierarchy -format ddc -output baseline.ddc
    write -hierarchy -format verilog -output baseline.v
    write_sdc -nosplit baseline.sdc
    puts "DC_STAGE: baseline_saved";flush stdout
} elseif {$Mode eq "hold"} {
    read_ddc $BaselineDdc
    current_design $Top
    if {![link]} {error "Baseline reload failed"}
    set_fix_hold [get_clocks CoreClock]
    if {![compile -incremental_mapping -only_hold_time]} {error "Hold compile failed"}
} else {error "Unknown DC mode"}
# Save before reports so a slow reporting step cannot discard a usable design.
write -hierarchy -format ddc -output candidate.ddc
write -hierarchy -format verilog -output candidate.v
write_sdc -nosplit candidate.sdc
puts "DC_STAGE: candidate_saved";flush stdout
foreach {Ref Count} $MacroCounts {
    if {[sizeof_collection [get_cells -hierarchical -filter "ref_name == $Ref"]]!=$Count} {error "Mapped macro count differs"}
}
redirect area.rpt {report_area -hierarchy}
redirect units.rpt {report_units}
redirect setup.rpt {report_timing -delay_type max -max_paths 20 -significant_digits 6}
redirect hold.rpt {report_timing -delay_type min -max_paths 20 -significant_digits 6}
redirect check_design.rpt {check_design}
redirect check_timing.rpt {check_timing}
redirect violations.rpt {report_constraint -all_violators}
redirect references.rpt {report_reference -hierarchy}
set F [open Metrics.tsv w]
puts $F "source_commit\t$SourceCommit"
puts $F "top\t$Top"
puts $F "period_ns\t[get_attribute [get_clocks CoreClock] period]"
puts $F "setup_wns_ns\t[PathSlack max]"
puts $F "hold_wns_ns\t[PathSlack min]"
puts $F "mapped_leaf_area_um2\t[LibraryLeafArea]"
set PrivateArea 0.0
foreach {Ref Count} $MacroCounts {
    set L [get_lib_cells -quiet */$Ref]
    if {[sizeof_collection $L]!=1} {error "Macro area library not unique: $Ref"}
    set PrivateArea [expr {$PrivateArea+$Count*[get_attribute $L area]}]
}
puts $F "sram_area_um2\t$PrivateArea"
if {[info exists AcceleratorScope]} {
    set AccelArea 0.0
    foreach_in_collection C [get_cells -hierarchical -filter "is_hierarchical == false && full_name =~ $AcceleratorScope/*"] {
        set L [get_lib_cells -quiet */[get_attribute $C ref_name]]
        if {[sizeof_collection $L]!=1} {error "Unresolved accelerator leaf"}
        set AccelArea [expr {$AccelArea+[get_attribute $L area]}]
    }
    puts $F "accelerator_leaf_area_um2\t$AccelArea"
}
close $F
saif_map -write_map name_map.txt
set_svf -off
puts "DC_REPORTS_COMPLETE"
} Why]} {puts stderr "DC_ERROR: $Why";puts stderr $::errorInfo;exit 2}
exit 0
