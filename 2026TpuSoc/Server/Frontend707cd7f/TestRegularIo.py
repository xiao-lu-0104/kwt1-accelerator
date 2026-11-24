"""Exercise real IO Tcl with an API mock, then independent coordinate auditing."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from PinPlan import validate

HERE=Path(__file__).resolve().parent


class NativeProtocol(unittest.TestCase):
    def case(self, mode):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            result=subprocess.run(['tclsh',str(HERE/'TestRegularIo.tcl'),str(d),mode],capture_output=True,text=True)
            self.assertTrue((d/'placed_707cd7f.def').is_file(),result.stdout+result.stderr)
            if mode=='missing':
                self.assertNotEqual(result.returncode,0)
                self.assertIn('Expected one physical signal terminal',result.stderr)
            else:
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('MACRO_PG_GEOMETRY_ERRORS 0',result.stdout)
                if mode=='moved':
                    with self.assertRaises(ValueError):validate(d)
                else:
                    self.assertEqual(validate(d)['port_count'],197)

    def test_actual_tcl_plan_constraints_and_export(self):self.case('ok')
    def test_actual_tcl_moved_coordinates_rejected(self):self.case('moved')
    def test_failed_terminal_export_retains_saved_def(self):self.case('missing')


if __name__=='__main__':unittest.main()
