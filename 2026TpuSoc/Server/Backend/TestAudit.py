"""Exercise vendor-style conditional module definitions without selecting one."""
import json
from pathlib import Path
import tempfile
import unittest

import audit_kwt_sp_macro as audit


class ConditionalModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        macro = self.root / 'RAMSP1024X16'
        (macro / 'verilog').mkdir(parents=True)
        (macro / 'lib').mkdir()
        self.model = macro / 'verilog/RAMSP1024X16.v'
        self.lib = macro / 'lib/RAMSP1024X16_tt_1p10v_1p10v_25c.lib'
        self.lib.write_text('''library (fixture) { time_unit : "1ns";
cell (RAMSP1024X16) { area : 123;
pin (CLK) { direction : input; clock : true; }
pin (Q) { direction : output; } } }''')
        self.out = self.root / 'report'
        self.out.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_conditional_variants_preserved_with_source_locations(self):
        text = '''/* A comment
 spanning two lines. */
`ifdef WITH_POWER
module RAMSP1024X16(Q, CLK, VDD);
output [15:0] Q; input CLK; inout VDD;
endmodule
`else
module RAMSP1024X16(Q, CLK);
output [15:0] Q; input CLK;
specify $width(posedge CLK, 1.0); endspecify
endmodule
`endif
'''
        self.model.write_text(text)
        summary = '\n'.join(audit.audit(str(self.root), str(self.out)))
        report = json.loads((self.out / 'evidence.json').read_text())
        self.assertEqual(report['raw_definition_count'], 2)
        self.assertIsNone(report['raw_declaration'])
        self.assertFalse(report['active_definition_selected'])
        self.assertEqual([d['line'] for d in report['raw_declarations']], [4, 8])
        self.assertIn('inout VDD;', summary)
        self.assertIn('3: `ifdef WITH_POWER', summary)
        self.assertIn('12: `endif', summary)
        self.assertIn('FOUNDRY_TIMING_STATUS: NOT_RUN', summary)
        self.assertIn('posedge CLK', (self.out / 'timing_checks_raw.txt').read_text())

    def test_missing_definition_rejected(self):
        self.model.write_text('module WRONG; endmodule')
        with self.assertRaisesRegex(ValueError, 'No raw module'):
            audit.audit(str(self.root), str(self.out))

    def test_single_definition_still_requires_review(self):
        self.model.write_text('module RAMSP1024X16(Q,CLK); output Q; input CLK; endmodule')
        summary = '\n'.join(audit.audit(str(self.root), str(self.out)))
        self.assertIn('RAW_DEFINITION_COUNT: 1', summary)
        self.assertIn('ACTIVE_DEFINITION: NOT_SELECTED', summary)
        self.assertIn('PENDING_MANUAL_PORT_AND_DATASHEET_REVIEW', summary)

    def test_different_voltage_not_silently_selected(self):
        self.model.write_text('module RAMSP1024X16; endmodule')
        self.lib.rename(self.lib.with_name('RAMSP1024X16_tt_0p90v_0p90v_25c.lib'))
        with self.assertRaisesRegex(ValueError, 'no alternate source selected'):
            audit.audit(str(self.root), str(self.out))


if __name__ == '__main__':
    unittest.main()
