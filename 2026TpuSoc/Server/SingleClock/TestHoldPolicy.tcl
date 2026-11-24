# Policy tests with mock cells. This is not a DC execution.
set Here [file dirname [file normalize [info script]]]
source [file join $Here HoldPolicy.tcl]
proc Require {Condition Message} {if {![uplevel 1 [list expr $Condition]]} {error $Message}}
foreach Name {Cpu Cpu/ALU Bus Reset Tpu Tpu/Core Tpu/Core/Matmul Other/Tpu/Core/Sram/data} {
    Require {![InSram $Name]} "Scope widened unexpectedly: $Name"
}
foreach Name {{Tpu/Core/Sram/RequestWriteData_reg[0]} {Tpu/Core/Sram/Storage[0].Banks[0].Memory/Macro}} {
    Require {[InSram $Name]} "SRAM object omitted: $Name"
}
foreach Name {Tpu Tpu/Core Tpu/Core/Sram} {Require {[SramAncestor $Name]} "Ancestor omitted"}
Require {![SramAncestor Cpu] && ![SramAncestor Tpu/Core/Sram2]} "Wrong ancestors"
set F [file tempfile Path]
puts $F {create_clock -name CoreClock -period 6.666667 [get_ports Clock]}
puts $F {set_clock_uncertainty -hold 0.1 [get_clocks CoreClock]}
puts $F {set_false_path -from [get_ports ResetN]}
close $F
set Baseline [TimingSignature $Path]
set F [open $Path a]
puts $F {set_fix_hold [get_clocks CoreClock]}
puts $F {set_dont_touch [get_cells Cpu] true}
close $F
Require {$Baseline eq [TimingSignature $Path]} "Optimization permissions changed timing signature"
set F [open $Path a]
puts $F {set_false_path -to [get_pins SRAM/D]}
close $F
Require {$Baseline ne [TimingSignature $Path]} "New exception not caught"
file delete $Path
set A [dict create Cpu/g0 BUF Cpu/g1 FF]
set B [dict create Cpu/g1 FF Cpu/g0 BUF]
AssertSameReferences $A $B
Require {[catch {AssertSameReferences $A [dict create Cpu/g0 INV Cpu/g1 FF]}]} "Changed CPU cell accepted"
Require {[catch {AssertSameReferences $A [dict create Cpu/g0 BUF]}]} "Removed CPU cell accepted"
Require {[catch {AssertSameReferences $A [dict create Cpu/g0 BUF Cpu/g1 FF Bus/new BUF]}]} "Outside insertion accepted"
foreach Name {HoldPolicy.tcl RepairHold.tcl Reports.tcl} {
    set F [open [file join $Here $Name] r]
    set Text [read $F]
    close $F
    Require {[info complete $Text]} "Incomplete Tcl: $Name"
}
puts "PASS HOLD_POLICY: SRAM scope, timing-exception guard, outside-cell preservation; mocks only"
