if {[catch {
    set Input $::env(TPU_SYSTEM_LIB)
    set Output $::env(TPU_SYSTEM_DB)
    if {[file exists $Output]} {error "Refusing existing shared macro DB"}
    set F [open $Input r]; set Text [read $F]; close $F
    if {![regexp {library\s*\(\s*"?([^"\s\)]+)} $Text -> Library]} {error "Shared library name missing"}
    read_lib $Input
    write_lib $Library -format db -output $Output
    if {![file isfile $Output] || [file size $Output]==0} {error "No shared macro DB produced"}
    puts "SYSTEM_SHARED_LIB_COMPLETE: $Output"
} Why]} {
    puts stderr "SYSTEM_SHARED_LIB_ERROR: $Why"
    exit 1
}
exit 0
