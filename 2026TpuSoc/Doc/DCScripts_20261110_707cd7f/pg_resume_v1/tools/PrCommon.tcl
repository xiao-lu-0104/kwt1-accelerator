# Shared native-tool checks. All mutations are inside the new user workspace.
proc PrRecord {key value} {
    set f [open PrStatus.tsv a]
    puts $f "$key\t$value"
    close $f
    puts "PR_STAGE: $key $value"
}
proc PrNeed {name options} {
    if {![llength [info commands $name]]} {error "Installed command missing: $name"}
    set file "${name}_manual.txt"
    redirect $file [list man $name]
    set f [open $file r]
    set text [read $f]
    close $f
    while {[string first "\b" $text] >= 0} {
        if {![regsub -all ".\b" $text {} text]} {break}
    }
    if {[string first SYNTAX $text] < 0} {error "Installed syntax unavailable: $name"}
    foreach option $options {
        if {[string first $option $text] < 0} {error "Installed $name manual does not confirm $option"}
    }
}
proc PrStep {label command {booleanRequired 0}} {
    PrRecord STAGE $label
    set value [uplevel 1 $command]
    if {($booleanRequired && ![string is boolean -strict $value]) ||
        ([string is boolean -strict $value] && !$value)} {
        error "$label returned failure: $value"
    }
    return $value
}
proc PrReport {name args} {
    if {[llength [info commands $name]]} {
        if {[catch {redirect "${name}.rpt" [linsert $args 0 $name]} why]} {
            PrRecord REPORT_ERROR "$name $why"
        }
    } else {PrRecord REPORT_UNAVAILABLE $name}
}
