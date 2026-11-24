"""Verify diagnostic provenance and rejection of altered or unrelated runs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import PrepareGateDiag as diag


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root / 'tools'
        tools.mkdir()
        script = tools / 'fixture.py'
        script.write_bytes(b'# immutable fixture\n')
        manifest = tools / 'MANIFEST.sha256'
        manifest.write_bytes((diag.sha(script) + '  fixture.py\n').encode())
        self.tools_sha = diag.sha(manifest)
        candidate = self.root / 'candidate.v'
        candidate.write_bytes(b'// checkpoint fixture\n')
        vendor = self.root / 'vendor.v'
        vendor.write_bytes(b'// library fixture\n')
        (self.root / 'ReportInputs.json').write_text(json.dumps({'inputs': {}}))
        (self.root / 'GateInputs.json').write_text(json.dumps({
            'model_inputs_sha256': {}, 'copied_model_sha256': {},
            'candidate_sha256': diag.sha(candidate), 'vendor_model': str(vendor),
            'vendor_sha256': diag.sha(vendor)}))
        (self.root / 'runner.log').write_text(
            'SCOPE_STATUS: ALL_OUTSIDE_ADDITIONS_ARE_LIBRARY_BUFFERS\n'
            'RESULT: FAIL stage=simulate_ff1 exit=1\n')

    def test_selects_expected_unchanged_failure(self):
        self.assertEqual(diag.select(self.root, self.tools_sha), self.root)

    def test_refuses_modified_checkpoint(self):
        (self.root / 'candidate.v').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Gate input changed'):
            diag.select(self.root, self.tools_sha)

    def test_refuses_changed_tool_manifest(self):
        (self.root / 'tools/fixture.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Recovery tool changed'):
            diag.select(self.root, self.tools_sha)

    def test_refuses_other_failure_stage(self):
        path = self.root / 'runner.log'
        path.write_text(path.read_text().replace('simulate_ff1', 'gate_compile'))
        with self.assertRaisesRegex(ValueError, 'expected failed gate'):
            diag.select(self.root, self.tools_sha)

    def test_recheck_refuses_changed_diagnostic_input(self):
        source = self.root / 'candidate.v'
        (self.root / 'DiagInputs.json').write_text(json.dumps({'inputs': {str(source): diag.sha(source)}}))
        diag.recheck(self.root)
        source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Diagnostic input changed'):
            diag.recheck(self.root)


if __name__ == '__main__':
    unittest.main()
