"""Check window boundaries, strict golden gates and explicit power unit parsing."""
from pathlib import Path
import tempfile
import tkinter
import unittest
from PrepareTaskPower import instrument
from SummarizeTaskPower import parse_power, validate_activity


class TaskPowerTests(unittest.TestCase):
    def test_annotated_tcl_rejects_failed_read_or_power_license(self):
        for mode,expected in (('pass',0),('bad_saif',1),('power_error',1)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                interp=tkinter.Tcl()
                interp.setvar('Mode',mode)
                interp.setvar('env(TPU_TASK_CASE)',directory)
                for key in ('TPU_POWER_DDC','TPU_STDCELL_DB','TPU_SRAM_DB','TPU_TASK_SAIF'):
                    interp.setvar('env('+key+')',key)
                interp.eval(r'''
proc exit {code} {set ::TestExit $code; error TEST_EXIT}
proc read_ddc {args} {}
proc current_design {args} {}
proc link {} {return 1}
proc all_clocks {} {return Clock}
proc get_attribute {object attribute} {return 6.666667}
proc sizeof_collection {items} {return [llength $items]}
proc get_cells {args} {return [lrepeat 56 RAM]}
proc reset_switching_activity {args} {set ::ResetDone 1}
proc read_saif {args} {
    if {![info exists ::ResetDone]} {error "stale annotations"}
    if {[lindex $args 3] ne "SharedTest/Cpu/u_e203_cpu/u_e203_nice_core"} {error "wrong scope"}
    if {$::Mode eq "bad_saif"} {return 0}
    return 1
}
proc report_saif {args} {
    if {[llength $args]} {error "unsupported optional flag"}
    return COVERAGE
}
proc report_power {args} {
    if {$::Mode eq "power_error"} {error "Power analysis license unavailable"}
    if {[lindex $args 0] eq "-cell" && [llength [lindex $args 2]]!=56} {error "missing SRAM"}
    return POWER
}
proc report_units {} {return UNITS}
proc redirect {path body} {
    set value [uplevel 1 $body]
    set fd [open $path w]; puts $fd $value; close $fd
}
''')
                original=Path.cwd()
                try:
                    with self.assertRaises(tkinter.TclError):
                        interp.call('source',str(Path(__file__).with_name('TaskPower.tcl').resolve()))
                    self.assertEqual(int(interp.getvar('TestExit')),expected)
                    if mode=='pass':
                        self.assertTrue((Path(directory)/'private_sram_power.rpt').exists())
                        self.assertTrue((Path(directory)/'saif_hierarchy.rpt.error.txt').exists())
                finally:
                    import os
                    os.chdir(original)

    def test_only_passive_window_calls_are_inserted(self):
        # Use the actual benchmark so source changes cannot silently move markers.
        original=(Path(__file__).resolve().parents[2]/'Sim/SharedTest.sv').read_text()
        changed=instrument(original)
        recovered=changed.replace(' TaskActivity.StartWindow();','').replace(' TaskActivity.EndRequested = 1;','')
        self.assertEqual(recovered,original)
        self.assertLess(changed.index('TaskActivity.StartWindow();'),changed.index('do @(posedge Clock); while (!CommandReady);'))
        with self.assertRaises(ValueError): instrument(changed)

    def test_report_units_and_dynamic_sum(self):
        text='Cell Internal Power = 2.0 mW\nNet Switching Power = 250 uW\nTotal Dynamic Power = 2.25 mW\nCell Leakage Power = 100 nW\n'
        powers=parse_power(text)
        self.assertAlmostEqual(powers['total_w'],0.0022501)
        with self.assertRaises(ValueError): parse_power(text.replace('100 nW','100'))
        with self.assertRaises(ValueError): parse_power(text.replace('2.25 mW','9 mW'))

    def test_reject_wrong_saif_window_or_failed_golden(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            log='''PASS SHARED: kind=1 layers=1 values=25344 cycles=332348 DMA_read_bytes=45952 DMA_write_bytes=50688 loaded_bytes=45960
INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0
ICB_MIRROR_FINAL: divergence_observed=0
TASK_ACTIVITY_FINAL: started=1 stopped=1
TASK_ACTIVITY_END: cycles=332348 duration_ns=2215764.116
'''
            (root/'run.log').write_text(log)
            saif='(TIMESCALE 1 ps) (DURATION 2215764116) (TC 1) (TX 100) (TZ 0)'
            (root/'task.saif').write_text(saif)
            result=validate_activity(root,'ff1')
            self.assertEqual(result['TX_nonzero_entries'],1)
            self.assertAlmostEqual(result['duration_seconds'],0.002215764116)
            (root/'task.saif').write_text(saif.replace('2215764116','2215760000'))
            with self.assertRaises(ValueError): validate_activity(root,'ff1')
            (root/'task.saif').write_text(saif)
            (root/'run.log').write_text(log+'\nFatal: mismatch\n')
            with self.assertRaises(ValueError): validate_activity(root,'ff1')


if __name__=='__main__': unittest.main()
