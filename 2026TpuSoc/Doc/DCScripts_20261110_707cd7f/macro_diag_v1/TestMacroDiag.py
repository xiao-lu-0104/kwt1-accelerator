import csv
from pathlib import Path
import subprocess
import tempfile
import unittest
from MacroDiag import native_script,summarize
from BuildPr import HERE,ROOT


class Diag(unittest.TestCase):
    def test_generator_never_runs_pg_or_weakens_acceptance(self):
        text=native_script((ROOT/'Doc/DCScripts_20261110_707cd7f/pg_v1/tools/PgStage.tcl').read_text())
        self.assertNotIn('compile_pg',text)
        self.assertNotIn('create_pg_',text)
        self.assertIn('MdDump keepout',text)
        self.assertIn('MdDump legalized',text)
        self.assertIn('MACRO_DIAGNOSTIC_NATIVE_COMPLETE_NO_PG',text)

    def test_numeric_format_change_is_reported_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            for tag in ('opened','fixed','keepout','legalized'):
                rows=[]
                for i in range(120):
                    rows.append({'instance':'M'+str(i),'ref':'RAMSP1024X16','x1':'0','y1':'0','x2':'1','y2':'1',
                        'bbox_raw':'{0 0} {1 1}' if tag=='opened' else '{0.0 0.0} {1.0 1.0}',
                        'origin':'0 0' if tag=='opened' else '0.0 0.0','orientation':'R0','is_fixed':'true','physical_status':'fixed','pg_pin_count':'3','pg_pin_signature':'unchanged'})
                with (d/('macro_'+tag+'.tsv')).open('w') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
            s=summarize(d)
            self.assertEqual(s['legalized']['counts']['bbox_raw'],120)
            self.assertEqual(s['legalized']['counts']['bbox_numeric'],0)
            self.assertEqual(s['legalized']['counts']['origin'],120)
            self.assertEqual(s['legalized']['counts']['origin_numeric'],0)

    def native_case(self,move):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);tools=d/'tools';tools.mkdir();out=d/'stage'
            frozen=ROOT/'Doc/DCScripts_20261110_707cd7f/pg_v1/tools'
            for name in ('PrCommon.tcl','IoGeometry.tcl'):(tools/name).write_bytes((frozen/name).read_bytes())
            (tools/'Diagnose.tcl').write_text(native_script((frozen/'PgStage.tcl').read_text()))
            mock=(HERE/'TestPgStage.tcl').read_text().split('if {$Kind in {connectivity drc}}',1)[0]
            mock+=r'''
set DiagKeepout 0;set DiagFixed 0
rename get_attribute BaseAttr
proc get_attribute {C A} {
    set Cell [lindex [split $C /] 0]
    if {$A eq "origin"} {return [lindex [BaseAttr $Cell bbox] 0]}
    if {$A eq "orientation"} {return R0}
    if {$A eq "is_fixed"} {return $::DiagFixed}
    if {$A eq "physical_status"} {if {$::DiagFixed} {return fixed} else {return placed}}
    if {$A eq "bbox"} {
        set B [BaseAttr $Cell bbox]
        if {[string first / $C]>=0} {return $B}
        if {$::DiagKeepout} {
            lassign [concat {*}$B] X1 Y1 X2 Y2
            return [list [list [expr {$X1-1.12}] [expr {$Y1-1.12}]] [list [expr {$X2+1.12}] [expr {$Y2+1.12}]]]
        }
        return $B
    }
    return [BaseAttr $C $A]
}
proc get_pins args {set C [lindex $args end];return [list $C/VDDCE $C/VDDPE $C/VSSE]}
proc set_fixed_objects args {set ::DiagFixed 1;return 1}
proc create_keepout_margin args {set ::DiagKeepout 1;return 1}
proc legalize_placement args {if {$::Bad eq "move"} {set ::Mutated 1};return 1}
source [file join $Tools Diagnose.tcl]
'''
            wrapper=d/'Mock.tcl';wrapper.write_text(mock)
            result=subprocess.run(['tclsh',str(wrapper),str(tools),str(out),'legalize','move' if move else ''],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue((out/'diagnostic_only.def').is_file())
            data=summarize(out)
            self.assertEqual(data['fixed']['counts']['bbox_numeric'],0)
            self.assertEqual(data['keepout']['counts']['bbox_numeric'],120)
            self.assertEqual(data['keepout']['counts']['pg_pin_signature'],0)
            self.assertEqual(data['legalized']['counts']['origin'],1 if move else 0)
            self.assertEqual(data['legalized']['counts']['origin_numeric'],1 if move else 0)
            self.assertEqual(data['legalized']['counts']['pg_pin_signature'],1 if move else 0)
            self.assertEqual(data['legalized']['incomplete_pg_pin_capture'],0)

    def test_actual_diagnostic_tcl_separates_keepout_bbox(self):self.native_case(False)
    def test_actual_diagnostic_tcl_detects_real_motion(self):self.native_case(True)


if __name__=='__main__':unittest.main()
