# Inspect output Boolean functions of all library references added outside SRAM.
if {[catch {
set Out $::env(TPU_GATE_WORK)
set target_library [list $::env(TPU_STDCELL_DB)]
set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
cd $Out
read_ddc [string trim [read [set F [open candidate_ddc.txt r]]]]
close $F
current_design e203_subsys_nice_core
if {![link]} {error "Candidate link failed"}
source ChangedRefs.tcl
set F [open buffer_functions.tsv w]
set AllBuffers 1
foreach Ref $ChangedRefs {
    set Lib [get_lib_cells -quiet */$Ref]
    if {[sizeof_collection $Lib] != 1} {error "Unknown or ambiguous library cell: $Ref"}
    set Inputs [get_lib_pins -of_objects $Lib -filter {direction == in}]
    set Outputs [get_lib_pins -of_objects $Lib -filter {direction == out}]
    set Buffer 0
    set Function ""
    if {[sizeof_collection $Inputs] == 1 && [sizeof_collection $Outputs] == 1} {
        set Function [get_attribute $Outputs function]
        set Input [file tail [get_object_name $Inputs]]
        set Normalized [string map [list " " "" "(" "" ")" "" "\t" ""] $Function]
        if {$Normalized eq $Input} {set Buffer 1}
    }
    if {!$Buffer} {set AllBuffers 0}
    puts $F "$Ref\t$Buffer\t$Function"
    puts "ADDED_CELL_FUNCTION: $Ref; noninverting_buffer=$Buffer; function=$Function"
}
close $F
set F [open BuffersOnly.txt w]
puts $F $AllBuffers
close $F
puts "BUFFER_FUNCTION_AUDIT_COMPLETE: $AllBuffers"
} Error]} {
    puts stderr "BUFFER_AUDIT_ERROR: $Error"
    exit 1
}
exit 0
