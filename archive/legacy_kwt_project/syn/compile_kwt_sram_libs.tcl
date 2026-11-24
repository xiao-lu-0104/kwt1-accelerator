# Run: lc_shell -f syn/compile_kwt_sram_libs.tcl
# Only writes a private DB cache; never modifies the supplied foundry library.
# TT 1.1V/25C is a synthesis corner, not a worst-corner timing signoff.
if {[catch {
set root [file normalize [file join [file dirname [info script]] ..]]
set sram_root /storage1/admin_public_dir/SRAM_Lib_2025
set db_dir [file join $root syn sram_db]
if {[info exists ::env(KWT_SRAM_DIR)]} {set sram_root $::env(KWT_SRAM_DIR)}
if {[info exists ::env(KWT_SRAM_DB_DIR)]} {set db_dir $::env(KWT_SRAM_DB_DIR)}
file mkdir $db_dir
foreach macro {RAMTP1024X16 RAMTP128X16} {
    set sources [glob -nocomplain [file join $sram_root $macro lib ${macro}_tt_1p10v_1p10v_25c.lib]]
    if {[llength $sources] != 1} {error "Need one 1.1V/25C/TT Liberty for $macro; found $sources"}
    set source [lindex $sources 0]
    set fp [open $source r]
    set contents [read $fp]
    close $fp
    if {![regexp {library\s*\(\s*"?([^"\s\)]+)} $contents -> lib_name]} {
        error "Cannot find library name in $source"
    }
    if {![regexp [format {cell\s*\(\s*"?%s"?\s*\)} $macro] $contents]} {
        error "$source does not contain the expected cell $macro"
    }
    set output [file join $db_dir [file rootname [file tail $source]].db]
    set temporary "${output}.new_[pid]_[clock seconds]"
    if {[file exists $temporary]} {error "Temporary output already exists: $temporary"}
    read_lib $source
    write_lib $lib_name -format db -output $temporary
    if {![file exists $temporary] || [file size $temporary] == 0} {error "No DB produced: $temporary"}
    file rename -force $temporary $output
    puts "SRAM_DB: $output"
}
puts "DONE: private TT SRAM DB cache at $db_dir"
puts "KWT_SRAM_DB_COMPLETE"
} task_error]} {
    puts stderr "KWT_ERROR: $task_error"
    exit 1
}
exit 0
