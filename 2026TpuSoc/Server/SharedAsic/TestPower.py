"""Check provenance gates, physical-area correlation and SAIF time units."""
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from PreparePower import lef_geometry, select, CASES
from SummarizePower import compare_area, saif_duration_seconds


class PowerTests(unittest.TestCase):
    def run_preflight_mock(self, root, mode):
        """Exercise the actual Tcl flow; this is not a DC/tool validation."""
        interp = tkinter.Tcl()
        interp.setvar('TestMode', mode)
        interp.setvar('env(TPU_POWER_OUT)', str(root))
        for name in ('TPU_STDCELL_DB', 'TPU_SRAM_DB', 'TPU_POWER_DDC'):
            interp.setvar('env('+name+')', name)
        interp.eval(r'''
proc exit {code} {set ::TestExit $code; error TEST_EXIT}
proc read_ddc {args} {}
proc current_design {args} {}
proc link {} {return 1}
proc all_clocks {} {return Clock}
proc sizeof_collection {items} {return [llength $items]}
proc get_attribute {object attribute} {
    switch $attribute {
        period {return 6.666667}
        ref_name {return $object}
        area {
            if {$object eq "RAMSP1024X16"} {return 9148.524414}
            if {$::TestMode eq "bad_area"} {return 0}
            return 190955.016
        }
    }
    error "Unexpected attribute $attribute"
}
proc get_cells {args} {
    set macros [lrepeat 56 RAMSP1024X16]
    if {[lindex $args end] eq "ref_name == RAMSP1024X16"} {
        if {$::TestMode eq "bad_macros"} {return [lrange $macros 1 end]}
        return $macros
    }
    return [concat $macros LOGIC]
}
proc report_units {args} {}
proc report_area {args} {}
proc get_lib_cells {args} {return [string range [lindex $args end] 2 end]}
proc get_libs {} {return {StdLib SramLib}}
proc get_object_name {object} {return $object}
proc foreach_in_collection {var items body} {
    upvar 1 $var item
    foreach item $items {uplevel 1 $body}
}
proc redirect {path body} {uplevel 1 $body}
if {$::TestMode eq "broken_docs"} {
    proc read_saif {args} {}
    proc report_power {args} {}
    proc report_lib {args} {error "Unavailable library documentation"}
    proc help {args} {error "Unavailable help"}
    proc man {args} {error "Unavailable manual"}
}
''')
        original = Path.cwd()
        try:
            with self.assertRaises(tkinter.TclError):
                interp.call('source', str(Path(__file__).with_name('PowerPreflight.tcl').resolve()))
            return int(interp.getvar('TestExit'))
        finally:
            # Tcl cd changes the process working directory too.
            import os
            os.chdir(original)

    def test_optional_commands_absent_or_broken_do_not_abort(self):
        for mode in ('absent_docs', 'broken_docs'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                self.assertEqual(self.run_preflight_mock(root, mode), 0)
                self.assertTrue((root/'area_metrics.tsv').exists())
                caps=(root/'capabilities.tsv').read_text()
                self.assertIn('read_saif\t'+('1' if mode=='broken_docs' else '0'), caps)
                self.assertTrue(list((root/'help').glob('*.error.txt')))
                self.assertIn('clock_period_ns\t6.666667', (root/'checkpoint_context.txt').read_text())

    def test_critical_macro_and_area_guards_still_abort(self):
        for mode in ('bad_macros', 'bad_area'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.assertEqual(self.run_preflight_mock(Path(directory), mode), 1)
                self.assertFalse((Path(directory)/'area_metrics.tsv').exists())

    def test_lef_nested_pin_end_and_multiple_macros(self):
        text = 'MACRO BUF\n SIZE 0.8 BY 1.6 ;\n PIN A\n END A\nEND BUF\nMACRO RAM\n SIZE 10 BY 20 ;\nEND RAM\n'
        values = lef_geometry(text)
        self.assertAlmostEqual(values['BUF']['area_um2'],1.28)
        self.assertEqual(values['RAM']['area_um2'],200)

    def test_area_requires_every_used_reference_and_all_variants(self):
        rows, complete = compare_area([('BUF',4,1.28),('RAM',1,200)], {'BUF':[{'area_um2':1.28}]})
        self.assertFalse(complete)
        self.assertEqual(rows[1]['status'],'MISSING_OR_INCONSISTENT_LEF')
        _, complete = compare_area([('BUF',4,1.28)], {'BUF':[{'area_um2':1.28},{'area_um2':2.56}]})
        self.assertFalse(complete)

    def test_saif_converts_units_and_rejects_empty_window(self):
        self.assertAlmostEqual(saif_duration_seconds('(TIMESCALE 10 ps) (DURATION 32000)'),320e-9)
        with self.assertRaises(ValueError): saif_duration_seconds('(TIMESCALE 1 ns) (DURATION 0)')

    def test_provenance_requires_complete_golden_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'InventoryInputs.json').write_text(json.dumps({'inputs':{}}))
            (root/'runner.log').write_text('RESULT: GATE_INVENTORY_COMPLETE\n')
            for case,(kind,values,cycles) in CASES.items():
                (root/(case+'.log')).write_text(f'PASS SHARED: kind={kind} layers=1 values={values} cycles={cycles} DMA_read_bytes=0\nICB_MIRROR_FINAL: divergence_observed=0\nINIT_FINAL: released=1 checked=1 new_control_QX=0\n')
            selected,_=select(root)
            self.assertEqual(selected,root.resolve())
            (root/'encoder_all_pattern2.log').write_text('Fatal: missing encoder result')
            with self.assertRaises(ValueError): select(root)


if __name__=='__main__': unittest.main()
