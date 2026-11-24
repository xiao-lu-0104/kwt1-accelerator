"""Check model selection, missing-model refusal and immutable mapped inputs."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import PrepareGate as gate


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_selects_combined_library_and_udp_support(self):
        combined = self.root / 'cells.v'
        combined.write_text('module BUF_X1(input I, output Z); assign Z=I; endmodule\n'
                            'module FF_X1(input D, output Q); udpff f(Q,D); endmodule\n')
        other = self.root / 'buf.v'
        other.write_text('module BUF_X1(input I, output Z); assign Z=I; endmodule\n')
        udp = self.root / 'udp.v'
        udp.write_text('primitive udpff(Q,D); output Q; input D; table 0:0; 1:1; endtable endprimitive\n')
        selected, missing = gate.choose_models({'BUF_X1', 'FF_X1'}, [other, udp, combined])
        self.assertEqual(selected, [combined, udp])
        self.assertFalse(missing)

    def test_comments_do_not_create_fake_coverage(self):
        path = self.root / 'comments.v'
        path.write_text('// module MISSING(); endmodule\n/* module OTHER(); endmodule */\nmodule REAL(); endmodule\n')
        selected, missing = gate.choose_models({'REAL', 'MISSING'}, [path])
        self.assertEqual(selected, [path])
        self.assertEqual(missing, {'MISSING'})

    def test_compressed_vendor_model_is_supported(self):
        path = self.root / 'cells.v.gz'
        path.write_bytes(gzip.compress(b'module BUF_X1(input I,output Z); assign Z=I; endmodule\n'))
        selected, missing = gate.choose_models({'BUF_X1'}, [path])
        self.assertEqual(selected, [path])
        self.assertFalse(missing)

    def test_missing_models_stay_missing(self):
        selected, missing = gate.choose_models({'BUF_X1'}, [])
        self.assertEqual(selected, [])
        self.assertEqual(missing, {'BUF_X1'})

    def test_modified_candidate_is_rejected(self):
        candidate = self.root / 'candidate.v'
        candidate.write_bytes(b'mapped checkpoint')
        vendor = self.root / 'vendor.v'
        vendor.write_bytes(b'vendor model')
        (self.root / 'ReportInputs.json').write_text(json.dumps({'inputs': {}}))
        record = {'model_inputs_sha256': {}, 'copied_model_sha256': {},
                  'candidate_sha256': gate.sha(candidate), 'vendor_model': str(vendor),
                  'vendor_sha256': gate.sha(vendor)}
        (self.root / 'GateInputs.json').write_text(json.dumps(record))
        gate.recheck_gate(self.root)
        candidate.write_bytes(b'changed checkpoint')
        with self.assertRaisesRegex(ValueError, 'Gate input changed'):
            gate.recheck_gate(self.root)


if __name__ == '__main__':
    unittest.main()
