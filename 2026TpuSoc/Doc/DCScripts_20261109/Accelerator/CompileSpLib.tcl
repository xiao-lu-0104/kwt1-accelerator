# Private conversion of the reviewed TT Liberty. Shared libraries stay read-only.
if {[catch {
set Input [file join $::env(TPU_SRAM_ROOT) RAMSP1024X16 lib RAMSP1024X16_tt_1p10v_1p10v_25c.lib]
set Output $::env(TPU_SRAM_DB)
if {[file exists $Output]} {error "Refusing to replace an existing DB"}
set F [open $Input r]
set Text [read $F]
close $F
if {![regexp {library\s*\(\s*"?([^"\s\)]+)} $Text -> Library]} {error "Missing library name"}
read_lib $Input
write_lib $Library -format db -output $Output
if {![file isfile $Output] || [file size $Output] == 0} {error "No SRAM DB produced"}
puts "SP_LIBRARY_COMPLETE: $Output"
} Error]} {
    puts stderr "ASIC_ERROR: $Error"
    exit 1
}
exit 0
