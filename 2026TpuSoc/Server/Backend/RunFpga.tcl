# Reproduce the latest upstream FPGA backend, with explicit per-run clocks.
# No RTL edits, no foundry-macro claim, no blanket asynchronous-clock cut.
# args: run-name top tpu-period-ns cpu-period-ns
set Root [file normalize [file join [file dirname [info script]] ../..]]
if {$argc != 4} { error "Need run-name, top, TPU period and CPU period" }
lassign $argv Run Top TpuPeriod CpuPeriod
if {![regexp {^[A-Za-z0-9][A-Za-z0-9-]*$} $Run]} {error "Invalid run name"}
if {$Top ni {TpuNiceAxi E203Tpu}} {error "Unsupported top"}
foreach Period [list $TpuPeriod $CpuPeriod] {
    if {![string is double -strict $Period] || $Period <= 0} {error "Invalid clock period"}
}
set Out [file join $Root workspace Backend $Run]
if {[file exists [file join $Out Sources.txt]]} {error "Existing run; choose a new name"}
file mkdir $Out
cd $Out
set_param general.maxThreads 4
set Snapshot [file join $Out Sources]
file mkdir $Snapshot
set Sha [auto_execok sha256sum]
if {$Sha eq "" && $tcl_platform(platform) eq "windows"} {
    set Sha [list {C:/Program Files/Git/usr/bin/sha256sum.exe}]
}
if {$Sha eq ""} {error "sha256sum unavailable"}
set Manifest [open [file join $Out Sources.txt] w]
puts $Manifest "Vivado [version -short]; top $Top; TPU period $TpuPeriod ns; CPU period $CpuPeriod ns"
puts $Manifest "FPGA xc7a100tcsg324-1 OOC; 1ns input jitter; inferred BRAM, no foundry SRAM"
proc SnapshotFile {Source Destination} {
    global Sha Manifest
    file mkdir [file dirname $Destination]
    file copy -force $Source $Destination
    puts $Manifest [exec {*}$Sha $Destination]
    return $Destination
}
foreach Name {TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer TpuMatmul TpuGelu TpuVector TpuDma TpuTop TpuNice TpuAxi TpuNiceAxi} {
    read_verilog -sv [SnapshotFile [file join $Root Rtl $Name.sv] [file join $Snapshot $Name.sv]]
}
if {$Top eq "E203Tpu"} {
    foreach Name {TpuCdc TpuResetSync E203Tpu} {
        read_verilog -sv [SnapshotFile [file join $Root Rtl $Name.sv] [file join $Snapshot $Name.sv]]
    }
    set CpuRoot [file join $Snapshot e203_hbirdv2 rtl e203]
    set CpuFiles {}
    foreach Folder {core general} {
        foreach Original [lsort [glob [file join $Root e203_hbirdv2 rtl e203 $Folder *.v]]] {
            lappend CpuFiles [SnapshotFile $Original [file join $CpuRoot $Folder [file tail $Original]]]
        }
    }
    set_property include_dirs [list [file join $CpuRoot core]] [current_fileset]
    set_property verilog_define FPGA_SOURCE [current_fileset]
    read_verilog $CpuFiles
}
set ClockFile [file join $Snapshot AppliedTiming.xdc]
set F [open $ClockFile w]
if {$Top eq "E203Tpu"} {
    puts $F "create_clock -name TpuClock -period $TpuPeriod \[get_ports Clock\]"
    puts $F "create_clock -name CpuClock -period $CpuPeriod \[get_ports CpuClock\]"
    puts $F {set_input_jitter [get_clocks TpuClock] 1.000}
    puts $F {set_input_jitter [get_clocks CpuClock] 1.000}
    # Common async assertion; each domain synchronizes reset release in RTL.
    puts $F {set_false_path -from [get_ports ResetN]}
} else {
    puts $F "create_clock -name CoreClock -period $TpuPeriod \[get_ports Clock\]"
    puts $F {set_input_jitter [get_clocks CoreClock] 1.000}
}
close $F
puts $Manifest [exec {*}$Sha $ClockFile]
read_xdc $ClockFile
synth_design -top $Top -part xc7a100tcsg324-1 -mode out_of_context
if {$Top eq "E203Tpu"} {
    set CdcFile [file join $Snapshot AppliedCdc.tcl]
    set F [open $CdcFile w]
    puts $F {set FirstStage [get_cells -hier -regexp {.*(RequestSynchronizer|AcknowledgeSynchronizer)_reg\[0\]}]}
    puts $F {if {[llength $FirstStage] != 4} {error "Expected four toggle first stages"}}
    puts $F {set_false_path -to [get_pins -of_objects $FirstStage -filter {REF_PIN_NAME == D}]}
    foreach {Channel Period} [list RequestChannel $TpuPeriod ResponseChannel $CpuPeriod] {
        puts $F "set Channel $Channel"
        puts $F "set Period $Period"
        puts $F {set Source [get_cells -hier -filter "NAME =~ *${Channel}*SourcePayload_reg*"]}
        puts $F {set Destination [get_cells -hier -filter "NAME =~ *${Channel}*DestinationData_reg*"]}
        puts $F {if {![llength $Source] || ![llength $Destination]} {error "Bundled-data endpoints missing"}}
        puts $F {set_max_delay -datapath_only $Period -from $Source -to $Destination}
        puts $F {set_bus_skew $Period -from $Source -to $Destination}
    }
    close $F
    puts $Manifest [exec {*}$Sha $CdcFile]
    source $CdcFile
}
close $Manifest
report_utilization -file SynthUtilization.rpt
report_timing_summary -file SynthTiming.rpt
write_checkpoint -force Synth.dcp
opt_design
place_design
phys_opt_design -directive Explore
route_design -directive Explore
if {[get_property SLACK [get_timing_paths -max_paths 1]] < 0} {
    phys_opt_design -directive Explore
    route_design -directive Explore
}
report_timing_summary -file RouteTiming.rpt
report_timing -delay_type max -max_paths 20 -file SetupPaths.rpt
report_timing -delay_type min -max_paths 20 -file HoldPaths.rpt
report_utilization -file RouteUtilization.rpt
report_utilization -hierarchical -file HierarchyUtilization.rpt
report_clock_interaction -file ClockInteraction.rpt
report_exceptions -file Exceptions.rpt
report_drc -file Drc.rpt
if {$Top eq "E203Tpu"} {
    report_cdc -details -file Cdc.rpt
    report_bus_skew -file BusSkew.rpt
    foreach Group {CpuClock TpuClock} {
        report_timing -group $Group -delay_type max -max_paths 10 -file ${Group}Setup.rpt
        report_timing -group $Group -delay_type min -max_paths 10 -file ${Group}Hold.rpt
    }
    foreach Channel {RequestChannel ResponseChannel} {
        set From [get_cells -hier -filter "NAME =~ *${Channel}*SourcePayload_reg*"]
        set To [get_cells -hier -filter "NAME =~ *${Channel}*DestinationData_reg*"]
        report_timing -from $From -to $To -delay_type max -max_paths 10 -file ${Channel}MaxDelay.rpt
    }
}
write_checkpoint -force Route.dcp
puts "BACKEND_REPORTS_COMPLETE: $Out"
