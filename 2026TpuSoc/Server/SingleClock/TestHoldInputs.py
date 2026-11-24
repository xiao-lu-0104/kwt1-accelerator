"""Test recovery provenance guards with disposable fixtures, not EDA inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hold_inputs', HERE/'VerifyHoldInputs.py')
hold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hold)


class InputsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tpusoc-hold-test-')
        self.root = Path(self.temp.name)
        self.original = self.root/'original'
        self.work = self.root/'work'
        self.work.mkdir()
        self.original.mkdir()
        self.saved_manifest = hold.MANIFEST
        self.source = self.original/'project/Rtl/Example.sv'
        self.write(self.source, b'module Example; endmodule\n')
        manifest = (hashlib.sha256(self.source.read_bytes()).hexdigest()+'  Rtl/Example.sv\n').encode()
        self.write(self.original/'package_manifest.sha256', manifest)
        hold.MANIFEST = hashlib.sha256(manifest).hexdigest()
        self.write(self.original/'logs/vcs_run_SpBindingTest.log', b'PASS SP_BINDING: fixture\n')
        self.write(self.original/'logs/library.log', b'SP_LIBRARY_COMPLETE: fixture\n')
        self.write(self.original/'E203TpuBackend/summary.txt',
                   ('SOURCE_COMMIT: '+hold.COMMIT+'\nASIC_REPORTS_COMPLETE: fixture\n').encode())
        self.ddc = self.original/'E203TpuBackend/E203TpuBackend_mapped.ddc'
        self.write(self.ddc, b'FAKE DDC\n')
        self.std = self.original/'standard.db'
        self.sp = self.original/'sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db'
        self.write(self.std, b'FAKE STANDARD DB\n')
        self.write(self.sp, b'FAKE SRAM DB\n')
        self.write(self.original/'library_sha256.txt', ''.join(
            hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p)+'\n'
            for p in (self.std, self.sp)).encode())

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def tearDown(self):
        hold.MANIFEST = self.saved_manifest
        self.temp.cleanup()

    def prepare(self):
        hold.prepare(str(self.original), str(self.work))

    def test_copy_and_recheck(self):
        self.prepare()
        self.assertEqual(self.ddc.read_bytes(), (self.work/'input.ddc').read_bytes())
        hold.recheck(str(self.work))

    def test_source_change_rejected(self):
        self.source.write_bytes(b'CHANGED')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.prepare()

    def test_library_change_rejected(self):
        self.std.write_bytes(b'CHANGED')
        with self.assertRaisesRegex(ValueError, 'library changed'):
            self.prepare()

    def test_missing_vendor_pass_rejected(self):
        (self.original/'logs/vcs_run_SpBindingTest.log').write_bytes(b'FAIL')
        with self.assertRaisesRegex(ValueError, 'passing evidence'):
            self.prepare()

    def test_original_checkpoint_change_detected(self):
        self.prepare()
        self.ddc.write_bytes(b'CHANGED')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            hold.recheck(str(self.work))

    def test_wrong_manifest_rejected(self):
        hold.MANIFEST = '0'*64
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.prepare()


if __name__ == '__main__':
    unittest.main()
