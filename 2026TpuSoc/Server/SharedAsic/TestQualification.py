"""Qualification guards, fail-closed result parsing and Power Compiler query calls."""
import os
from pathlib import Path
import tempfile
import unittest
import time
from unittest.mock import patch
from PrepareQualification import guard
from SummarizeQualification import task_status


def fixture_candidate():
    return '''module e203_subsys_nice_core;
wire nice_rst_n=1;
TpuTop Tpu();
endmodule
module TpuTop;
TpuCore Core();
endmodule
module TpuCore;
TpuMatmul Matrix();
TpuDma Dma();
'''+'\n'.join('RAMSP1024X16 \\Storage[%d].Memory (.CLK(SharedTest.Clock),.CEN(1\'b0),.GWEN(SharedTest.Cycles[0]),.WEN(16\'h0000),.A(10\'h0),.D(16\'h1234),.Q(),.RET1N(1\'b1));'%i for i in range(56))+'''
endmodule
module TpuMatmul;
TpuDot Dot();
TpuRowBuffer BiasBuffer();
endmodule
module TpuDot;
wire InputValid=!$test$plusargs("EMPTY_DOT");
wire [127:0] InputOperandA=128'h123,InputOperandB=128'h456;
endmodule
module TpuRowBuffer;
wire WriteValid=1;
wire [127:0] WriteData=128'h789;
endmodule
module TpuDma;
wire WriteDataValid=1,ReadDataValid=1,ReadDataReady=1,ReadDataLast=0,ReadDataError=0;
wire SramReadValid=1,SramReadReady=1;
wire [127:0] WriteData=128'h123,ReadData=128'h456,SramReadData=128'h789;
endmodule
'''


def write_fixtures(out):
    candidate=fixture_candidate()
    (out/'candidate.sv').write_text(candidate)
    (out/'EffectiveDataGuard.sv').write_text(guard(candidate))
    (out/'Fixture.sv').write_text('''`timescale 1ns/1ps
module LocalQualificationTop;
SharedTest SharedTest();
TaskActivity TaskActivity();
EffectiveDataGuard EffectiveDataGuard();
endmodule
module SharedTest;
logic Clock=0;
longint unsigned Cycles=0,StartCycle=0,LastWriteCycle=0;
e203_subsys_nice_core CpuRoot();
// Match the hierarchy used by the actual DUT observers.
FixtureCpu Cpu();
initial forever begin #3.333 Clock=1; #3.334 Clock=0; end
always @(posedge Clock) Cycles<=Cycles+1;
initial begin
repeat(4) @(negedge Clock); StartCycle=Cycles+1; TaskActivity.StartWindow();
repeat(10) @(posedge Clock); #0.001; LastWriteCycle=Cycles; TaskActivity.EndRequested=1;
wait(TaskActivity.Stopped); #0.01;
if (!EffectiveDataGuard.Complete) $fatal(1,"GUARD_NOT_COMPLETE");
$display("PASS LOCAL_QUALIFICATION_WINDOW: original ten-cycle boundaries and exercised observers"); $finish;
end
endmodule
module FixtureCpu;
FixtureCore u_e203_cpu();
endmodule
module FixtureCore;
e203_subsys_nice_core u_e203_nice_core();
endmodule
module RAMSP1024X16(input CLK,CEN,GWEN,RET1N,input [15:0] WEN,D,input [9:0] A,output [15:0] Q);
assign Q=16'h0;
endmodule
''')
    (out/'MacroFixture.sv').write_text('''`timescale 1ns/1ps
// Local contract fixture only. Actual manufacturer model is used on server.
module RAMSP4096X16(output logic [15:0] Q,input CLK,CEN,GWEN,input [15:0] WEN,D,
input [11:0] A,input [2:0] EMA,input [1:0] EMAW,input RET1N);
logic [15:0] Memory[4096];
always @(posedge CLK) if (!CEN) begin
if (!GWEN) begin
for (int B=0;B<16;B++) if ($test$plusargs("BAD_MASK") ? WEN[B] : !WEN[B]) Memory[A][B]<=D[B];
end else Q<=Memory[A];
end
endmodule
''')


class QualificationTests(unittest.TestCase):
    def test_large_leaf_inventory_never_researches_whole_candidate(self):
        candidate=fixture_candidate().replace('TpuDma Dma();', 'TpuDma Dma();\n'+
            '\n'.join('DQV0_12TR40 U%d (.D(value[%d]),.CK(Clock),.Q(q[%d]));'%(i,i,i)
                      for i in range(20000)))
        original_search=__import__('re').search
        def bounded_search(pattern,text,*args,**kwargs):
            if text is candidate: raise AssertionError('Per-object full-netlist search regressed')
            return original_search(pattern,text,*args,**kwargs)
        started=time.monotonic()
        with patch('PrepareQualification.re.search',side_effect=bounded_search): result=guard(candidate)
        self.assertEqual(result.count('MACRO_ENABLE_X'),56)
        print('LARGE_NETLIST_CHECK: leaf_cells=20000 bytes='+str(len(candidate))+
              ' elapsed_seconds='+format(time.monotonic()-started,'.3f'))

    def test_recursive_or_duplicate_modules_rejected(self):
        candidate=fixture_candidate()
        with self.assertRaisesRegex(ValueError,'Recursive mapped hierarchy'):
            guard(candidate.replace('TpuDma Dma();','TpuCore Dma();'))
        with self.assertRaisesRegex(ValueError,'Duplicate candidate module'):
            guard(candidate+'\nmodule TpuDot; endmodule\n')

    def test_generation_preserves_escaped_macro_path_and_missing_signal_fails(self):
        candidate=fixture_candidate(); text=guard(candidate)
        self.assertIn('\\Storage[0].Memory .CEN',text)
        self.assertEqual(text.count('MACRO_ENABLE_X'),56)
        with self.assertRaisesRegex(ValueError,'observed signal missing'):
            guard(candidate.replace('InputOperandB','RemovedOperand'))

    def test_result_requires_both_function_and_effective_data_completion(self):
        text='''PASS SHARED: kind=1 layers=1 values=25344 cycles=332348 rest
INIT_FINAL: released=1 checked=1 new_control_QX=0
ICB_MIRROR_FINAL: divergence_observed=0
PASS EFFECTIVE_DATA_GUARD:
EFFECTIVE_GUARD_FINAL: complete=1'''
        self.assertTrue(task_status(text,'ff1'))
        self.assertFalse(task_status(text.replace('complete=1','complete=0'),'ff1'))
        self.assertFalse(task_status(text+'\nFatal: effective data X','ff1'))
        self.assertFalse(task_status(text,'encoder'))

    def test_real_clock_tcl_has_no_unsupported_pt_options_and_fails_critical_errors(self):
        import tkinter
        for mode,expected in (('pass',0),('bad_saif',1),('bad_macros',1),('bad_query',1),('bad_report',0)):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                original=Path.cwd(); interp=tkinter.Tcl()
                interp.setvar('Mode',mode); interp.setvar('env(TPU_QUAL_CASE)',directory)
                for key in ('TPU_STDCELL_DB','TPU_SRAM_DB','TPU_POWER_DDC','TPU_QUAL_SAIF'):
                    interp.setvar('env('+key+')',key)
                interp.eval(r'''
proc exit {code} {set ::TestExit $code; error TEST_EXIT}
proc read_ddc {args} {}
proc current_design {args} {}
proc link {} {return 1}
proc all_clocks {} {return Clock}
proc sizeof_collection {objects} {return [llength $objects]}
proc get_attribute {object attribute} {return 6.666667}
proc get_cells {args} {return [lrepeat [expr {$::Mode eq "bad_macros" ? 55 : 56}] RAM]}
proc reset_switching_activity {args} {set ::ResetDone 1}
proc read_saif {args} {
if {![info exists ::ResetDone]} {error "stale annotation"}
return [expr {$::Mode ne "bad_saif"}]
}
proc help {args} {return HELP}
proc report_activity {args} {
if {[llength $args] || $::Mode eq "bad_report"} {error "unsupported report"}
return ACTIVITY
}
proc get_nets {args} {return {nice_clk Bus/Clock Tpu/Clock Tpu/Core/Clock}}
proc get_object_name {object} {return $object}
proc foreach_in_collection {variable objects body} {
foreach item $objects {uplevel 1 [list set $variable $item]; uplevel 1 $body}
}
proc get_switching_activity {args} {
if {[llength $args]!=1 || [string match -* [lindex $args 0]] || $::Mode eq "bad_query"} {error "query failed"}
return {(probability = 0.5,toggle_rate = 0.299985,type = annotated)}
}
rename puts original_puts
proc puts {args} {
if {[llength $args]==1} {return [lindex $args 0]}
return [uplevel 1 [linsert $args 0 original_puts]]
}
proc redirect {args} {
if {[lindex $args 0] eq "-variable"} {uplevel 1 [list set [lindex $args 1] [uplevel 1 [lindex $args 2]]]; return}
set value [uplevel 1 [lindex $args 1]]
set fd [open [lindex $args 0] w]; original_puts $fd $value; close $fd
}
''')
                try:
                    with self.assertRaises(tkinter.TclError):
                        interp.call('source',str(Path(__file__).with_name('QualificationClock.tcl').resolve()))
                    self.assertEqual(int(interp.getvar('TestExit')),expected)
                    if expected==0: self.assertEqual(len((Path(directory)/'clocks.txt').read_text().splitlines()),4)
                finally: os.chdir(original)


if __name__=='__main__':
    import sys
    if len(sys.argv)==3 and sys.argv[1]=='--fixtures': write_fixtures(Path(sys.argv[2]))
    else: unittest.main()
