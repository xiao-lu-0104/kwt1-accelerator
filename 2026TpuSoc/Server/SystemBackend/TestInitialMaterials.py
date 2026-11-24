"""Test source joins, immutable evidence, tampering and relocated numerical checks."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

from InitialMaterials import merge, sha, verify, write_manifest
from MakeInitialMaterials import build_files, NUMERICAL, ROOT


def fixture(base):
    backend = base / 'backend'
    original = backend / 'BackendRawMaterials'
    original.mkdir(parents=True)
    shutil.copytree(ROOT / 'workspace/Server/tpusoc_shared_20261105_v1', original / 'Sources/Team',
                    ignore=shutil.ignore_patterns('MANIFEST.sha256', '__pycache__'))
    (original / 'Provenance').mkdir()
    shutil.copy2(ROOT / 'workspace/Server/tpusoc_shared_20261105_v1/MANIFEST.sha256',
                 original / 'Provenance/OriginalBundleManifest.sha256')
    (original / 'Simulation').mkdir()
    (original / 'Simulation/Task.f').write_text('/original/server/cpu.v\n+incdir+/original/server/include\n', encoding='utf-8')
    summary = {'tasks': {name: {'power': {'cycles': cycles}} for name, cycles in
               (('ff1', 332354), ('encoder', 1485719))},
               'limitations': ['TEST FIXTURE: no real server power report is synthesized by this test.']}
    (original / 'BackendMaterialsSummary.json').write_text(json.dumps(summary), encoding='utf-8')
    write_manifest(original)
    archive = backend / 'BackendRawMaterials.partial.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        for path in sorted(original.rglob('*')):
            if path.is_file():
                stream.add(path, arcname='BackendRawMaterials/' + path.relative_to(original).as_posix())
    supplement = base / 'supplement'
    for name, data in build_files().items():
        path = supplement / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    out = base / 'out'
    out.mkdir()
    return backend, supplement, out, sha(archive)


class InitialMaterialTests(unittest.TestCase):
    def test_real_vectors_replay_and_candidate_relocates_without_changing_evidence(self):
        with tempfile.TemporaryDirectory(prefix='initial_material_test_') as directory:
            backend, supplement, out, digest = fixture(Path(directory))
            before = {p: sha(p) for parent in (backend, supplement) for p in parent.rglob('*') if p.is_file()}
            with contextlib.redirect_stdout(io.StringIO()):
                merge(backend, supplement, out, digest)
            root = out / 'InitialMaterials'
            status = json.loads((root / 'ReviewStatus.json').read_text(encoding='utf-8'))
            self.assertEqual(status['numerical_replay'], 'PASS_FIXED_POINT_HEX_REPLAY')
            self.assertEqual(status['vector_sha256_matches'], 86)
            self.assertTrue(status['remaining'])
            verify(root)
            relocated = Path(directory) / 'relocated candidate with spaces'
            shutil.move(str(root), relocated)
            run = subprocess.run([sys.executable, '-B', str(relocated / 'Reproduce/CheckInitialMaterials.py'),
                                  '--replay'], cwd=directory, capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('NUMERICAL_REPLAY: PASS', run.stdout)
            verify(relocated)
            for path, value in before.items():
                self.assertEqual(sha(path), value)

    def test_changed_backend_vector_cannot_join_even_with_rewritten_local_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            backend, supplement, out, digest = fixture(Path(directory))
            root = backend / 'BackendRawMaterials'
            (root / 'Sources/Team/Vectors/Input.hex').write_text('00000000\n', encoding='utf-8')
            write_manifest(root)
            with self.assertRaisesRegex(ValueError, 'manifest differs'):
                merge(backend, supplement, out, digest)

    def test_failed_numerical_result_cannot_be_reported_as_a_complete_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            backend, supplement, out, digest = fixture(Path(directory))
            helper = supplement / 'CheckSharedHex.py'
            helper.write_text('raise SystemExit(7)\n', encoding='utf-8')
            write_manifest(supplement)
            with self.assertRaisesRegex(ValueError, 'Numerical replay failed'):
                merge(backend, supplement, out, digest)
            self.assertFalse((out / 'InitialMaterials.candidate.tar.gz').exists())

    def test_missing_dependency_is_retained_as_unperformed_not_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            backend, supplement, out, digest = fixture(Path(directory))
            helper = supplement / 'CheckSharedHex.py'
            helper.write_text("import json,sys\nfrom pathlib import Path\n"
                              "p=Path(sys.argv[sys.argv.index('--out')+1])\n"
                              "p.write_text(json.dumps({'status':'DEPENDENCY_UNAVAILABLE'}))\n"
                              "raise SystemExit(3)\n", encoding='utf-8')
            write_manifest(supplement)
            with contextlib.redirect_stdout(io.StringIO()):
                merge(backend, supplement, out, digest)
            review = json.loads((out / 'InitialMaterials/ReviewStatus.json').read_text(encoding='utf-8'))
            self.assertEqual(review['numerical_replay'], 'DEPENDENCY_UNAVAILABLE')
            self.assertTrue(any('NumPy is unavailable' in value for value in review['remaining']))

    def test_modified_quantized_expected_output_is_rejected_by_the_model(self):
        with tempfile.TemporaryDirectory() as directory:
            vectors = Path(directory) / 'vectors'
            shutil.copytree(ROOT / 'workspace/Server/tpusoc_shared_20261105_v1/Vectors', vectors)
            path = vectors / 'Ff1_normal/Expected0.hex'
            lines = path.read_text(encoding='utf-8').splitlines()
            lines[0] = format(int(lines[0], 16) ^ 1, '08x')
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            run = subprocess.run([sys.executable, '-B', str(ROOT / 'Server/SystemBackend/CheckSharedHex.py'),
                '--vectors', str(vectors), '--model', str(NUMERICAL / 'Model'),
                '--out', str(Path(directory) / 'result.json')], capture_output=True, text=True, timeout=60)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('Numerical mismatch', run.stderr)


if __name__ == '__main__':
    unittest.main()
