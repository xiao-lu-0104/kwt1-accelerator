from pathlib import Path
import subprocess
import tempfile
import unittest
from BuildPg import build_files

HERE=Path(__file__).resolve().parent


class Stage(unittest.TestCase):
    def case(self,kind,bad=''):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            for n,b in build_files().items():
                p=d/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            out=d/'stage'
            result=subprocess.run(['tclsh',str(HERE/'TestPgStage.tcl'),str(d/'tools'),str(out),kind,bad],capture_output=True,text=True)
            if bad:
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertTrue((out/'pg_complete.def').is_file())
                self.assertIn('MACRO_REF_BBOX changed',result.stdout+result.stderr)
            else:self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return result.stdout+result.stderr

    def test_legalize_saves_before_legality(self):self.case('legalize')
    def test_pg42_macro_exclusions_and_long_pin_adapter(self):
        s=self.case('pg_core');self.assertIn('CHECKPOINT_SAVED pg_complete',s)
    def test_moved_macro_cannot_pass(self):self.case('pg_core','move')
    def test_zero_return_check_is_execution_not_boolean_failure(self):self.case('connectivity')
    def test_separate_drc_check(self):self.case('drc')


if __name__=='__main__':unittest.main()
