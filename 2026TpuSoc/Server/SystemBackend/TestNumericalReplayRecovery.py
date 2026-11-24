"""Verify dependency recovery preserves the old candidate and real numerical outputs."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from InitialMaterials import merge, sha, verify, write_manifest
from RecoverNumericalReplay import recover
from TestInitialMaterials import fixture, ROOT

NUMERICAL = ROOT / 'workspace/Checks/InitialNumerics_20261106_hrz58ess/NumericalMaterial.partial.tar.gz'


def missing_candidate(base):
    backend, supplement, out, digest = fixture(base)
    (supplement / 'CheckSharedHex.py').write_text(
        "import json,sys\nfrom pathlib import Path\n"
        "Path(sys.argv[sys.argv.index('--out')+1]).write_text(json.dumps({'status':'DEPENDENCY_UNAVAILABLE'}))\n"
        "raise SystemExit(3)\n", encoding='utf-8')
    write_manifest(supplement)
    with contextlib.redirect_stdout(io.StringIO()):
        merge(backend, supplement, out, digest)
    recovery = base / 'recovery'
    recovery.mkdir()
    return out, recovery, sha(out / 'InitialMaterials.candidate.tar.gz')


class RecoveryTests(unittest.TestCase):
    def test_replay_runs_without_site_packages_and_relocated_candidate_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, digest = missing_candidate(Path(directory))
            before = verify(source / 'InitialMaterials')
            with contextlib.redirect_stdout(io.StringIO()):
                recover(source, out, ROOT / 'Server/SystemBackend/CheckSharedHexScalar.py', digest, NUMERICAL)
            root = out / 'InitialMaterials'
            verify(root)
            review = json.loads((root / 'ReviewStatus.json').read_text(encoding='utf-8'))
            self.assertEqual(review['numerical_replay'], 'PASS_FIXED_POINT_HEX_REPLAY')
            self.assertEqual(review['numerical_replay_implementation'], 'PYTHON_STDLIB_SCALAR')
            self.assertEqual(review['previous_numerical_replay'], 'DEPENDENCY_UNAVAILABLE')
            self.assertEqual(len(review['float_parameter_sha256']), 37)
            for name, value in review['float_parameter_sha256'].items():
                self.assertEqual(sha(root / 'Project/workspace/Model/official' / name), value)
            self.assertFalse(any('NumPy is unavailable' in item for item in review['remaining']))
            self.assertTrue(review['remaining'])
            self.assertEqual(verify(source / 'InitialMaterials'), before)
            self.assertEqual(sha(source / 'InitialMaterials.candidate.tar.gz'), digest)
            renamed = Path(directory) / 'moved candidate with spaces'
            root.rename(renamed)
            check = subprocess.run([sys.executable, '-B', '-S', str(renamed / 'Reproduce/CheckInitialMaterials.py')],
                                   cwd=directory, capture_output=True, text=True, timeout=60)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_failed_replay_does_not_produce_a_new_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, digest = missing_candidate(Path(directory))
            scalar = Path(directory) / 'FailingScalar.py'
            scalar.write_text('raise SystemExit(8)\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'replay failed'):
                recover(source, out, scalar, digest, NUMERICAL)
            self.assertFalse((out / 'InitialMaterials.candidate.tar.gz').exists())

    def test_rewritten_source_manifest_cannot_replace_original_archive_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, digest = missing_candidate(Path(directory))
            root = source / 'InitialMaterials'
            (root / 'Project/Vectors/Input.hex').write_text('00000000\n', encoding='utf-8')
            write_manifest(root)
            with self.assertRaisesRegex(ValueError, 'manifest differs'):
                recover(source, out, ROOT / 'Server/SystemBackend/CheckSharedHexScalar.py', digest, NUMERICAL)


if __name__ == '__main__':
    unittest.main()
