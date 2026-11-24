from pathlib import Path
import subprocess
import tempfile
import unittest
from BuildPr import HERE
from BuildPgResume import build_files


class ResumeStage(unittest.TestCase):
    def case(self,bad=''):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tools=root/'tools';tools.mkdir()
            files=build_files()
            for n,b in files.items():
                p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            self.assertNotIn(b'legalize_placement',files['tools/PgStage.tcl'])
            mock=(HERE/'TestPgStage.tcl').read_text().split('if {$Kind in {connectivity drc}}',1)[0]
            mock+=r'''
rename get_attribute RawAttr
proc get_attribute {Object A} {
    set C [lindex [split $Object /] 0]
    if {$A eq "origin"} {return [lindex [RawAttr $C bbox] 0]}
    if {$A eq "orientation"} {return R0}
    if {$A eq "is_fixed"} {return true}
    if {$A eq "bbox" && [string first T: $Object]==0 && $::Kind eq "pg_core" && $::Bad eq "pre_io"} {
        return {{10 100} {10.07 100.07}}
    }
    if {$A eq "bbox" && [string first macro $C]==0} {
        set B [RawAttr $C bbox]
        if {[string first / $Object]>=0 || $::Kind eq "audit_baseline"} {return $B}
        lassign [concat {*}$B] A B C D
        return [list [list [expr {$A-1.12}] [expr {$B-1.12}]] [list [expr {$C+1.12}] [expr {$D+1.12}]]]
    }
    return [RawAttr $Object $A]
}
proc get_pins args {
    if {[lsearch -exact $args -of_objects]<0} {return PG_PIN}
    set C [lindex $args end]
    return [list $C/VDDCE $C/VDDPE $C/VSSE]
}
rename set_pg_strategy BaseStrategy
proc set_pg_strategy args {
    set V [BaseStrategy {*}$args]
    if {[lindex $args 0] eq "S_MESH707"} {
        set Poly [lindex [lindex [lindex $::MeshBlockages 0] 1] 1]
        set X2 [lindex [lindex $Poly 1] 0]
        if {abs($X2-108.58)>1e-6} {error "Keepout halo was applied twice: X2=$X2"}
        puts "ORIGINAL_BBOX_PLUS_SINGLE_HALO_CONFIRMED"
    }
    return $V
}
if {$Kind eq "pg_core"} {
    set Audit [lindex $argv 4]
    set F [open PgConfig.tcl a]
    puts $F "set BaselineLeaves {[file join $Audit BaselineLeaves.tsv]}"
    puts $F "set BaselineMacros {[file join $Audit BaselineMacros.tsv]}"
    puts $F "set BaselineBoxes {[file join $Audit SourceMacroBoxes.tsv]}"
    puts $F "set BaselineIo {[file join $Audit PortTerminalGeometry.tsv]}"
    close $F
    if {$Bad eq "pre_move"} {set Mutated 1}
    if {$Bad eq "pre_leaf"} {dict set Refs c0 CHANGED_REF}
}
source [file join $Tools PgStage.tcl]
'''
            script=root/'Mock.tcl';script.write_text(mock)
            audit=root/'audit'
            first=subprocess.run(['tclsh',str(script),str(tools),str(audit),'audit_baseline',''],capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            for n in ('BaselineLeaves.tsv','BaselineMacros.tsv','SourceMacroBoxes.tsv'):
                self.assertTrue((audit/n).is_file())
            out=root/'recovered'
            second=subprocess.run(['tclsh',str(script),str(tools),str(out),'pg_core',bad,str(audit)],capture_output=True,text=True)
            log=second.stdout+second.stderr
            if bad:
                self.assertNotEqual(second.returncode,0,log)
                if bad.startswith('pre_'):self.assertFalse((out/'ring.def').exists())
                else:self.assertTrue((out/'pg_complete.def').is_file())
            else:
                self.assertEqual(second.returncode,0,log)
                self.assertIn('ORIGINAL_BBOX_PLUS_SINGLE_HALO_CONFIRMED',log)
                self.assertIn('RECOVERY_BASELINE_MATCH LOGICAL_LEAVES_AND_MACRO_PHYSICAL_IDENTITY',log)
            return log

    def test_keepout_bbox_difference_passes_real_physical_identity(self):self.case()
    def test_preexisting_macro_motion_rejected_before_pg(self):
        self.assertIn('SOURCE_MACRO_PHYSICAL_IDENTITY changed',self.case('pre_move'))
    def test_changed_logic_rejected_before_pg(self):
        self.assertIn('SOURCE_LOGICAL_MAP changed',self.case('pre_leaf'))
    def test_real_macro_motion_during_pg_still_rejected(self):
        self.assertIn('MACRO_PHYSICAL_IDENTITY changed',self.case('move'))
    def test_changed_io_rejected_before_pg(self):
        self.assertIn('RECOVERED_IO_CHANGED_BEFORE_PG',self.case('pre_io'))


if __name__=='__main__':unittest.main()
