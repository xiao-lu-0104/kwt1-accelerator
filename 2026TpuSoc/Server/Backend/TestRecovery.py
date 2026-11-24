"""Test reuse guards with fixture logs/DBs; does not execute VCS or DC."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'workspace/Server/tpusoc_a1d0c9a_asic_20261102_v3b'
SCRIPT = Path(__file__).with_name('RecoverAsic.sh').read_text()
CODE = SCRIPT.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.parent = (ROOT / 'workspace/Checks').resolve()
        self.temp = tempfile.TemporaryDirectory(prefix='RecoveryTest-', dir=self.parent)
        self.base = Path(self.temp.name).resolve()
        self.assertTrue(self.base.is_relative_to(self.parent))
        self.original = self.base / 'original'
        self.project = self.original / 'project'
        self.project.mkdir(parents=True)
        for name in ('Rtl', 'Server', 'Sim', 'e203_hbirdv2'):
            shutil.copytree(SOURCE / name, self.project / name)
        shutil.copyfile(SOURCE / 'MANIFEST.sha256', self.original / 'package_manifest.sha256')
        logs = self.original / 'logs'
        logs.mkdir()
        (logs / 'vcs_run_SpBindingTest.log').write_text('FIXTURE ONLY: PASS SP_BINDING:')
        (logs / 'vcs_run_CdcTest.log').write_text('FIXTURE ONLY: PASS CDC:')
        (logs / 'library.log').write_text('FIXTURE ONLY: SP_LIBRARY_COMPLETE:')
        self.standard = self.original / 'standard.db'
        self.sram = self.original / 'sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db'
        self.sram.parent.mkdir()
        self.standard.write_bytes(b'fixture standard DB, not an EDA model')
        self.sram.write_bytes(b'fixture macro DB, not an EDA model')
        (self.original / 'library_sha256.txt').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p) + '\n'
            for p in (self.standard, self.sram)))
        self.output = self.base / 'recovery'
        self.output.mkdir()

    def tearDown(self):
        self.assertTrue(self.base.is_relative_to(self.parent))
        self.temp.cleanup()

    def invoke(self):
        return subprocess.run([sys.executable, '-c', CODE, str(self.original), str(self.output)],
                              capture_output=True, text=True)

    def test_removes_only_unused_parameter_and_preserves_original(self):
        original_adapter = self.project / 'Server/Backend/SpFoundry.sv'
        before = original_adapter.read_bytes()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(original_adapter.read_bytes(), before)
        after = (self.output / 'project/Server/Backend/SpFoundry.sv').read_bytes()
        expected = Path(__file__).with_name('SpFoundry.sv').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(after, expected)
        record = json.loads((self.output / 'recovery.json').read_text())
        self.assertEqual(record['new_adapter_sha256'], hashlib.sha256(expected).hexdigest())

    def test_modified_rtl_rejected(self):
        target = self.project / 'Rtl/TpuSram.sv'
        target.write_bytes(target.read_bytes() + b'\n// changed fixture\n')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Original project differs', result.stderr)

    def test_modified_cached_db_rejected(self):
        self.sram.write_bytes(b'changed fixture library')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cached library differs', result.stderr)


if __name__ == '__main__':
    unittest.main()
