"""Join a verified server backend archive with a small numerical-source supplement."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify(root):
    root = root.resolve()
    manifest = root / 'MANIFEST.sha256'
    entries = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or name in entries:
            raise ValueError('Unsafe or duplicate manifest path: ' + name)
        path = root / relative
        if root not in path.resolve().parents or path.is_symlink() or not path.is_file():
            raise ValueError('Missing/unsafe manifest file: ' + name)
        if sha(path) != digest:
            raise ValueError('Material checksum mismatch: ' + name)
        entries[name] = digest
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != manifest}
    if actual != set(entries):
        raise ValueError('Manifest does not enumerate every file')
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Unexpected symbolic link')
    return entries


def write_manifest(root):
    files = sorted(p for p in root.rglob('*') if p.is_file() and p.name != 'MANIFEST.sha256')
    # Nested manifests are evidence and must themselves be covered by the outer manifest.
    files += sorted(p for p in root.rglob('MANIFEST.sha256') if p != root / 'MANIFEST.sha256')
    (root / 'MANIFEST.sha256').write_text(''.join(
        sha(p) + '  ' + p.relative_to(root).as_posix() + '\n' for p in sorted(files)), encoding='utf-8')


def merge(backend, supplement, out, expected_backend_sha):
    archive = backend / 'BackendRawMaterials.partial.tar.gz'
    if sha(archive) != expected_backend_sha:
        raise ValueError('Backend archive differs from the recorded successful package')
    original = backend / 'BackendRawMaterials'
    with tarfile.open(archive, 'r:gz') as stream:
        archived = stream.extractfile('BackendRawMaterials/MANIFEST.sha256')
        if archived is None or archived.read() != (original / 'MANIFEST.sha256').read_bytes():
            raise ValueError('Backend source manifest differs from the recorded archive')
    before = verify(original)
    extra_before = verify(supplement)
    meta = json.loads((supplement / 'NumericalMaterial.json').read_text(encoding='utf-8'))
    if sha(original / 'Provenance/OriginalBundleManifest.sha256') != meta['frozen_bundle_manifest_sha256']:
        raise ValueError('Numerical and backend source baselines differ')
    vectors = original / 'Sources/Team/Vectors'
    if meta['matched_hex_files'] != 86 or len(meta['vector_sha256']) != 86:
        raise ValueError('Expected the verified 86-vector baseline')
    for name, digest in meta['vector_sha256'].items():
        path = vectors / name
        if vectors.resolve() not in path.resolve().parents or path.is_symlink() or sha(path) != digest:
            raise ValueError('Frozen numerical vector differs: ' + name)
    for path in (supplement / 'Model').glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    summary = json.loads((original / 'BackendMaterialsSummary.json').read_text(encoding='utf-8'))
    for name in ('ff1', 'encoder'):
        row = summary['tasks'][name]['power']
        expected_cycles = {'ff1': 332354, 'encoder': 1485719}[name]
        if row['cycles'] != expected_cycles:
            raise ValueError('Unexpected repaired-firmware task cycles: ' + name)
    root = out / 'InitialMaterials'
    root.mkdir()
    (root / 'Backend').mkdir()
    shutil.copy2(archive, root / 'Backend' / archive.name)
    (root / 'Backend/BackendRawMaterials.sha256').write_text(expected_backend_sha + '  ' + archive.name + '\n', encoding='utf-8')
    shutil.copytree(original / 'Sources/Team', root / 'Project')
    # Original team bundle has no numerical Model/ directory; never overwrite one silently.
    shutil.copytree(supplement / 'Model', root / 'Project/Model')
    shutil.copytree(supplement / 'NumericalDocs', root / 'NumericalDocs')
    shutil.copytree(supplement / 'CurrentDocs', root / 'CurrentDocs')
    (root / 'Provenance').mkdir()
    for name in ('NumericalMaterial.json', 'ParameterSources.json', 'Supplement.json'):
        shutil.copy2(supplement / name, root / 'Provenance' / name)
    shutil.copy2(supplement / 'MANIFEST.sha256', root / 'Provenance/NumericalSupplement.sha256')
    (root / 'Reproduce').mkdir()
    for name in ('CheckSharedHex.py', 'CheckInitialMaterials.py'):
        shutil.copy2(supplement / name, root / 'Reproduce' / name)
    (root / 'Checks').mkdir()
    # New directory and relative CLI paths exercise relocation of the numerical entry.
    command = [sys.executable, '-B', 'Reproduce/CheckSharedHex.py', '--vectors', 'Project/Vectors',
               '--model', 'Project/Model', '--out', 'Checks/NumericalReplay.json']
    with (root / 'Checks/NumericalReplay.log').open('x') as log:
        result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if result.returncode not in (0, 3):
        raise ValueError('Numerical replay failed; inspect Checks/NumericalReplay.log')
    replay = json.loads((root / 'Checks/NumericalReplay.json').read_text(encoding='utf-8'))
    if result.returncode == 0 and replay['status'] != 'PASS_FIXED_POINT_HEX_REPLAY':
        raise ValueError('Replay success lacks pass evidence')
    if result.returncode == 3 and replay['status'] != 'DEPENDENCY_UNAVAILABLE':
        raise ValueError('Unexpected numerical dependency status')
    model_status = replay['status']
    filelist = (original / 'Simulation/Task.f').read_text(encoding='utf-8')
    absolute_lines = [line for line in filelist.splitlines() if '/' in line and
                      (line.startswith('/') or '+/' in line or ' /' in line)]
    review = {'status': 'INITIAL_RAW_MATERIALS_CANDIDATE_REVIEW_REQUIRED',
              'backend_sha256': expected_backend_sha,
              'numerical_sources': 'CHECKSUMS_AND_PYTHON_SYNTAX_PASS',
              'vector_sha256_matches': 86, 'numerical_replay': model_status,
              'sources': {'backend': str(backend), 'supplement': str(supplement)},
              'backend_results': summary,
              'remaining': ['Default/X activity and excluded fixed-peripheral power boundary require review.',
                  'Official 600-sample numerical/NRMSE evidence is not established.',
                  'Original VCS Task.f retains server paths; full clean RTL/EDA reproduction is not yet established.',
                  'Extracted floating-point .npz/.npy data remain local; converter requires the documented external checkpoint.',
                  'Final submission channel and team acceptance remain unconfirmed.'],
              'original_simulation_absolute_reference_lines': absolute_lines}
    if result.returncode == 3:
        review['remaining'].append('Server NumPy is unavailable; numerical execution was not performed on this server.')
    (root / 'ReviewStatus.json').write_text(json.dumps(review, indent=2) + '\n', encoding='utf-8')
    (root / 'README.md').write_text(
        '# Initial raw-material candidate / 初赛原始材料候选包\n\n'
        'Backend/ retains the exact successful backend archive. Project/ contains the validated repaired firmware, '
        'RTL/driver/vectors, and the original numerical Model sources.\n'
        'Numerical sources are joined by the frozen source-manifest hash and all 86 vector hashes.\n'
        'Numerical replay: ' + model_status + '. A pass is model/HEX consistency, not RTL execution or speech accuracy.\n'
        'Check file integrity after relocation: python3 -B Reproduce/CheckInitialMaterials.py\n'
        'Optional numerical execution: python3 -B Reproduce/CheckInitialMaterials.py --replay\n'
        'These commands do not install tools, download data, or invoke DC/VCS. NumPy is needed only for replay.\n'
        'CurrentDocs contains updated report drafts; older Project/Doc and nested backend documents retain provenance.\n'
        'ExternalLibraries.json and reproduction Task.f remain inside the backend archive. '
        'Foundry libraries/models must remain in their authorized environment.\n\n'
        'ReviewStatus.json lists unresolved limits. This is not a complete portable RTL/EDA project or final submission acceptance.\n', encoding='utf-8')
    write_manifest(root)
    verify(root)
    if verify(original) != before or verify(supplement) != extra_before or sha(archive) != expected_backend_sha:
        raise ValueError('Original evidence changed during merge')
    output = out / 'InitialMaterials.candidate.tar.gz'
    with tarfile.open(output, 'x:gz') as stream:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                stream.add(path, arcname='InitialMaterials/' + path.relative_to(root).as_posix(), recursive=False)
    digest = sha(output)
    (out / 'InitialMaterials.sha256').write_text(digest + '  ' + output.name + '\n', encoding='utf-8')
    print('NUMERICAL_SOURCE_JOIN: PASS vectors=86 frozen_baseline=matched', flush=True)
    print('NUMERICAL_REPLAY:', model_status, flush=True)
    print('BACKEND_ORIGINALS_UNCHANGED: PASS', flush=True)
    print('INITIAL_MATERIAL_ARCHIVE:', output, 'bytes=' + str(output.stat().st_size), 'sha256=' + digest, flush=True)
    print('RESULT: INITIAL_RAW_MATERIALS_CANDIDATE_PACKAGED; inspect ReviewStatus.json; not final acceptance', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--supplement', type=Path, required=True)
    parser.add_argument('--backend-sha256', required=True)
    args = parser.parse_args()
    merge(args.backend.resolve(), args.supplement.resolve(), args.out.resolve(), args.backend_sha256)
