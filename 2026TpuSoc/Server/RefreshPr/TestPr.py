"""Checks source binding/geometry; no claim of actual ICC2 placement."""
import importlib.util
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'FinalBackend'))
spec=importlib.util.spec_from_file_location('NewPrRun',HERE/'Run.py')
pr=importlib.util.module_from_spec(spec);spec.loader.exec_module(pr)


class Tests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('tclsh'),'Tcl runtime required')
    def test_native_clock_mismatch_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            result=subprocess.run(['tclsh',str(HERE/'TestPlace.tcl'),d,'6.67'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode,2)
            self.assertIn(b'Imported CoreClock differs',result.stdout)
            self.assertFalse((Path(d)/'placed_1109.def').exists())

    def test_original_pg_lists_are_parsed_without_evaluation(self):
        sys.path.insert(0,str(HERE))
        from Resume import pg_list
        self.assertEqual(pg_list('set PrPowerPins [list {VDD} {VDDCE} {VDDPE}]','PrPowerPins'),['VDD','VDDCE','VDDPE'])
        with self.assertRaises(ValueError):pg_list('set PrPowerPins [exec unsafe]','PrPowerPins')

    def test_clock_serialization_is_exact_rounding(self):
        template='set_units -time ns -capacitance pF\ncreate_clock [get_ports clk] -name CoreClock -period %s -waveform {0 3.33333}\n'
        self.assertEqual(pr.serialized_clock(template%'6.66667'),'6.66667')
        self.assertEqual(pr.serialized_clock(template%'6.666667'),'6.666667')
        for value in ('6.67','6.66668','6.66666','6.666670','10.00000'):
            with self.assertRaises(ValueError):pr.serialized_clock(template%value)
        with self.assertRaises(ValueError):pr.serialized_clock((template%'6.66667').replace('-time ns','-time ps'))
    def test_safe_tcl_lists(self):
        self.assertEqual(pr.tlist('Refs',['/a b/r.ndm','/c/p.ndm']),'set Refs [list {/a b/r.ndm} {/c/p.ndm}]\n')
        with self.assertRaises(ValueError):pr.tlist('Refs',['/bad}path'])

    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'candidate.v';p.write_text('1109')
            bound={str(p):pr.sha(p)};pr.verify(bound);p.write_text('old')
            with self.assertRaises(ValueError):pr.verify(bound)

    def test_native_bbox_and_lef_delta_both_retained(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);stage=out/'design';stage.mkdir()
            (stage/'report_units.rpt').write_text('length : 1.00um\n')
            (stage/'core_bbox.txt').write_text('{0 0} {2000 2000}')
            (stage/'report_placement.rpt').write_text('Total hard macro to hard macro overlaps: 0\n')
            lines=['instance\tref\tx1\ty1\tx2\ty2']
            for i in range(120):
                x=(i%12)*150;y=(i//12)*150;ref='RAMSP1024X16' if i<56 else 'RAMSP4096X16'
                lines.append('new_cpu/macro%d\t%s\t%s\t%s\t%s\t%s'%(i,ref,x,y,x+82.46,y+111.1314))
            (stage/'macros.tsv').write_text('\n'.join(lines))
            lef={'RAMSP1024X16':[82.46,110.945],'RAMSP4096X16':[82.46,110.945]}
            pr.geometry(stage,out,lef)
            data=json.loads((out/'MacroGeometry.json').read_text())
            self.assertEqual(len(data['macros']),120)
            self.assertGreater(data['macros'][0]['native_bbox_area_minus_lef_um2'],15)
            (stage/'macros.tsv').write_text('\n'.join(lines[:2]+[lines[2].rsplit('\t',4)[0]+'\t0\t0\t82.46\t111.1314']+lines[3:]))
            with self.assertRaises(ValueError):pr.geometry(stage,out,lef)


if __name__=='__main__':unittest.main()
