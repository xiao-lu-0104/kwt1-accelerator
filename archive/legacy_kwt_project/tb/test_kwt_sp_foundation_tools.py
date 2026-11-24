"""Fail-closed evidence selection tests; no vendor library is redistributed."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_kwt_sp_macro as audit


class SpEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.macro = self.root / 'RAMSP1024X16'
        (self.macro / 'verilog').mkdir(parents=True)
        (self.macro / 'lib').mkdir()
        (self.macro / 'verilog/RAMSP1024X16.v').write_text('''
module RAMSP1024X16(Q, CLK, CEN, WEN, A, D);
output [15:0] Q; input CLK,CEN; input [15:0] WEN,D; input [9:0] A;
specify $width(posedge CLK, 1.0); endspecify
endmodule
''', encoding='utf-8')
        self.lib = self.macro / 'lib/RAMSP1024X16_tt_1p10v_1p10v_25c.lib'
        self.lib.write_text('''
library (fixture) { time_unit : "1ns";
cell (RAMSP1024X16) { area : 123.45;
pin (CLK) { direction : input; clock : true; }
pin (Q) { direction : output;
timing () { related_pin : "CLK"; timing_type : rising_edge; when : "CEN == 0"; }
} } }
''', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_evidence_keeps_review_and_timing_open(self):
        out = self.root / 'report'
        out.mkdir()
        summary = audit.audit(str(self.root), str(out))
        text = '\n'.join(summary)
        self.assertIn('LIB_CLOCK_PINS: CLK', text)
        self.assertIn('FOUNDRY_TIMING_STATUS: NOT_RUN', text)
        self.assertIn('PENDING_MANUAL_PORT_AND_DATASHEET_REVIEW', text)
        self.assertIn('posedge CLK', (out / 'timing_checks_raw.txt').read_text())
        self.assertFalse(any(out.glob('*.v')))

    def test_does_not_select_another_voltage_library(self):
        self.lib.rename(self.lib.with_name('RAMSP1024X16_tt_0p90v_0p90v_25c.lib'))
        out = self.root / 'report'
        out.mkdir()
        with self.assertRaisesRegex(ValueError, 'no alternate source selected'):
            audit.audit(str(self.root), str(out))
        self.assertTrue((out / 'inventory.txt').exists())

    def test_wrong_liberty_cell_is_rejected(self):
        self.lib.write_text(self.lib.read_text().replace('cell (RAMSP1024X16)', 'cell (OTHER)'))
        out = self.root / 'report'
        out.mkdir()
        with self.assertRaisesRegex(ValueError, 'matching Liberty cell'):
            audit.audit(str(self.root), str(out))

    def test_existing_report_is_not_overwritten(self):
        out = self.root / 'existing'
        out.mkdir()
        sentinel = out / 'keep.txt'
        sentinel.write_text('earlier evidence')
        result = subprocess.run([sys.executable, str(ROOT / 'tools/audit_kwt_sp_macro.py'),
                                 '--root', str(self.root), '--out-dir', str(out)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), 'earlier evidence')


if __name__ == '__main__':
    unittest.main()
