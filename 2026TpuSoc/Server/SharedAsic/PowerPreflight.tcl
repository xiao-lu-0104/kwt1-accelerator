# Read-only PPA capability and units check; do not optimize or save a design.
proc SaveOptionalDocumentation {Path Body} {
    if {[catch {uplevel 1 [list redirect $Path $Body]} Why]} {
        set Details $::errorInfo
        set F [open ${Path}.error.txt w]
        puts $F "$Why\n$Details"
        close $F
        puts "OPTIONAL_DOCUMENTATION_UNAVAILABLE: $Path"
    }
}
if {[catch {
set Out $::env(TPU_POWER_OUT)
set target_library [list $::env(TPU_STDCELL_DB)]
set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
cd $Out
read_ddc $::env(TPU_POWER_DDC)
current_design e203_subsys_nice_core
if {![link]} {error "Checkpoint link failed"}
set Clocks [all_clocks]
if {[sizeof_collection $Clocks] != 1 || abs([get_attribute $Clocks period]-6.666667) > 0.000001} {error "Expected original 150 MHz single clock"}
set Macros [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]
if {[sizeof_collection $Macros] != 56} {error "Expected 56 reviewed private SRAM macros"}
report_units > units.rpt
report_area -hierarchy > area.rpt
set F [open checkpoint_context.txt w]
puts $F "top\te203_subsys_nice_core"
puts $F "checkpoint\t$::env(TPU_POWER_DDC)"
puts $F "standard_cell_db\t$::env(TPU_STDCELL_DB)"
puts $F "private_sram_db\t$::env(TPU_SRAM_DB)"
puts $F "clock_period_ns\t[get_attribute $Clocks period]"
close $F
file mkdir help
set Caps [open capabilities.tsv w]
foreach Command {read_saif report_saif report_switching_activity reset_switching_activity report_power report_lib list_attributes} {
    set Exists [expr {[llength [info commands $Command]] > 0}]
    puts $Caps "$Command\t$Exists"
    if {$Exists} {
        SaveOptionalDocumentation [file join help ${Command}.txt] {help $Command}
        if {[llength [info commands man]]} {
            SaveOptionalDocumentation [file join help ${Command}_manual.txt] {man $Command}
        }
    }
}
close $Caps
set F [open used_lib_cells.tsv w]
puts $F "reference\tcount\tlibrary_area"
set Counts [dict create]
foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    set Ref [get_attribute $Cell ref_name]
    if {$Ref in {**logic_0** **logic_1**}} {continue}
    dict incr Counts $Ref
}
set TotalArea 0.0
dict for {Ref Count} $Counts {
    set LibCell [get_lib_cells -quiet */$Ref]
    if {[sizeof_collection $LibCell] != 1} {error "Unmapped/ambiguous reference: $Ref"}
    set Area [get_attribute $LibCell area]
    set TotalArea [expr {$TotalArea+$Count*$Area}]
    puts $F "$Ref\t$Count\t$Area"
}
close $F
if {abs($TotalArea-703272.383184)>0.02} {error "Candidate leaf area changed"}
set F [open area_metrics.tsv w]
puts $F "total_library_area\t$TotalArea"
puts $F "private_sram_library_area\t[expr {56.0*[get_attribute [get_lib_cells */RAMSP1024X16] area]}]"
close $F
foreach_in_collection Lib [get_libs] {
    set Name [get_object_name $Lib]
    set Safe [string map {/ _ : _} $Name]
    SaveOptionalDocumentation [file join help library_${Safe}.txt] {report_lib $Name}
}
puts "POWER_PREFLIGHT_DDC_COMPLETE: area=$TotalArea SRAM=56; read-only checkpoint and command documentation"
} Error]} {
    puts stderr "POWER_PREFLIGHT_ERROR: $Error"
    puts stderr $::errorInfo
    exit 1
}
exit 0
