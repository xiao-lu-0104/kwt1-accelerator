"""Add a no-NumPy numerical replay to a new candidate, preserving its predecessor."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from InitialMaterials import sha, verify, write_manifest

NUMERICAL_SHA256 = 'd6d63bb158523bb3423c735f6d793a54e613c29b4bd29c253ca3a7656ffb3b1b'


def restore_parameters(numerical, root):
    if sha(numerical) != NUMERICAL_SHA256:
        raise ValueError('Full numerical archive differs from the verified local material')
    destination = root / 'Project/workspace/Model/official'
    destination.mkdir(parents=True)
    copied = {}
    expected = {'Manifest.json'} | {kind + str(index) + suffix for index in range(12)
        for kind, suffix in (('Input', '.npy'), ('Output', '.npy'), ('Layer', '.npz'))}
    with tarfile.open(numerical, 'r:gz') as stream:
        manifest = stream.extractfile('NumericalMaterial/MANIFEST.sha256').read()
        entries = dict((name, digest) for digest, name in
                       (line.split('  ', 1) for line in manifest.decode('utf-8').splitlines()))
        metadata = stream.extractfile('NumericalMaterial/NumericalMaterial.json').read()
        if json.loads(metadata) != json.loads((root / 'Provenance/NumericalMaterial.json').read_text(encoding='utf-8')):
            raise ValueError('Full numerical data and candidate numerical sources differ')
        prefix = 'NumericalMaterial/ExtractedOfficialParameters/'
        for member in stream.getmembers():
            if not member.name.startswith(prefix):
                continue
            name = member.name[len(prefix):]
            if not member.isfile() or name not in expected or name in copied:
                raise ValueError('Unexpected extracted numerical parameter: ' + name)
            data = stream.extractfile(member).read()
            digest = hashlib.sha256(data).hexdigest()
            if digest != entries['ExtractedOfficialParameters/' + name]:
                raise ValueError('Numerical parameter checksum mismatch: ' + name)
            (destination / name).write_bytes(data)
            copied[name] = digest
        if set(copied) != expected:
            raise ValueError('Missing extracted numerical parameter files')
    (root / 'Provenance/FullNumericalMaterialManifest.sha256').write_bytes(manifest)
    return copied


def recover(source, out, scalar, expected_sha, numerical):
    original = source / 'InitialMaterials'
    archive = source / 'InitialMaterials.candidate.tar.gz'
    if sha(archive) != expected_sha:
        raise ValueError('Previous candidate archive differs from the recorded successful package')
    with tarfile.open(archive, 'r:gz') as stream:
        proof = stream.extractfile('InitialMaterials/MANIFEST.sha256')
        if proof is None or proof.read() != (original / 'MANIFEST.sha256').read_bytes():
            raise ValueError('Previous candidate manifest differs from its archive')
    originals = verify(original)
    old_review = json.loads((original / 'ReviewStatus.json').read_text(encoding='utf-8'))
    if old_review['numerical_replay'] != 'DEPENDENCY_UNAVAILABLE' or old_review['vector_sha256_matches'] != 86:
        raise ValueError('Expected the source-matched candidate missing the NumPy dependency')
    root = out / 'InitialMaterials'
    shutil.copytree(original, root)
    for name, destination in (('Checks/NumericalReplay.json', 'PreviousNumericalReplay.json'),
                              ('Checks/NumericalReplay.log', 'PreviousNumericalReplay.log'),
                              ('ReviewStatus.json', 'PreviousReviewStatus.json'),
                              ('MANIFEST.sha256', 'PreviousCandidateManifest.sha256'),
                              ('README.md', 'PreviousCandidateREADME.md')):
        shutil.copy2(original / name, root / 'Provenance' / destination)
    parameter_sha256 = restore_parameters(numerical, root)
    shutil.copy2(root / 'Reproduce/CheckSharedHex.py', root / 'Reproduce/CheckSharedHexNumpy.py')
    shutil.copy2(scalar, root / 'Reproduce/CheckSharedHexScalar.py')
    (root / 'Reproduce/CheckSharedHex.py').write_text(
        '"""Default offline replay uses only the Python standard library."""\n'
        'import runpy\nfrom pathlib import Path\n'
        'runpy.run_path(str(Path(__file__).resolve().with_name("CheckSharedHexScalar.py")), run_name="__main__")\n',
        encoding='utf-8')
    command = [sys.executable, '-B', '-S', 'Reproduce/CheckSharedHex.py', '--vectors', 'Project/Vectors',
               '--model', 'Project/Model', '--out', 'Checks/NumericalReplay.json']
    with (root / 'Checks/NumericalReplay.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if result.returncode != 0:
        raise ValueError('Standard-library numerical replay failed; inspect Checks/NumericalReplay.log')
    replay = json.loads((root / 'Checks/NumericalReplay.json').read_text(encoding='utf-8'))
    if replay['status'] != 'PASS_FIXED_POINT_HEX_REPLAY' or replay['implementation'] != 'PYTHON_STDLIB_SCALAR':
        raise ValueError('Missing standard-library replay pass evidence')
    if len(replay['ff1_cases']) != 15 or len(replay['encoder_layers']) != 12:
        raise ValueError('Incomplete numerical replay')
    review = dict(old_review)
    review.update({'numerical_replay': replay['status'], 'numerical_replay_implementation': replay['implementation'],
                   'previous_candidate_sha256': expected_sha,
                   'previous_numerical_replay': old_review['numerical_replay'],
                   'full_numerical_archive_sha256': NUMERICAL_SHA256,
                   'float_parameter_sha256': parameter_sha256,
                   'float_parameter_location': 'Project/workspace/Model/official'})
    review['remaining'] = [item for item in old_review['remaining']
        if item not in ('Server NumPy is unavailable; numerical execution was not performed on this server.',
            'Extracted floating-point .npz/.npy data remain local; converter requires the documented external checkpoint.')]
    review['remaining'].append('The scalar checker does not execute the original NumPy model or float-parameter converter; '
                              'their source and dependency declarations are retained separately.')
    (root / 'ReviewStatus.json').write_text(json.dumps(review, indent=2) + '\n', encoding='utf-8')
    (root / 'README.md').write_text(
        '# Initial raw-material candidate with standard-library numerical replay\n\n'
        'Numerical replay: PASS_FIXED_POINT_HEX_REPLAY, implementation PYTHON_STDLIB_SCALAR.\n'
        'All 15 FF1 cases and all 12 encoder-layer HEX outputs match the fixed-point scalar translation.\n'
        'This scalar implementation is tied to the unchanged frozen Reference.py SHA and was compared locally '
        'with its NumPy primitives, all encoder stages, and the frozen vectors.\n'
        'The server replay uses Python -S and only the standard library. No installation or network is required.\n'
        'All 37 extracted float-parameter/input/output/manifest files from the verified full numerical archive '
        'are now included under Project/workspace/Model/official, with their original SHA256 values.\n'
        'Reproduce/CheckSharedHexNumpy.py preserves the earlier NumPy entry; the original Model sources are unchanged.\n'
        'Previous dependency-unavailable evidence is retained under Provenance/.\n'
        'Check integrity: python3 -B Reproduce/CheckInitialMaterials.py\n'
        'Replay after relocation: python3 -B -S Reproduce/CheckInitialMaterials.py --replay\n\n'
        'Backend/, Project RTL/firmware/vectors and original numerical Model files are unchanged from the predecessor.\n'
        'Power default/X and fixed-peripheral boundaries, official numerical accuracy, '
        'full clean RTL/EDA reproduction, submission channel and final team acceptance still require review.\n'
        'Older CurrentDocs and Provenance record earlier stages; ReviewStatus.json and Checks/NumericalReplay.json '
        'give this candidate\'s current replay status. This is not a final acceptance claim.\n', encoding='utf-8')
    # Confirm that only replay entries/status and new provenance files changed.
    changed = {'Reproduce/CheckSharedHex.py', 'Checks/NumericalReplay.json', 'Checks/NumericalReplay.log',
               'README.md', 'ReviewStatus.json'}
    for name, digest in originals.items():
        if name not in changed and sha(root / name) != digest:
            raise ValueError('Unrelated material changed during replay: ' + name)
    write_manifest(root)
    verify(root)
    if verify(original) != originals or sha(archive) != expected_sha:
        raise ValueError('Previous candidate changed during replay')
    output = out / 'InitialMaterials.candidate.tar.gz'
    with tarfile.open(output, 'x:gz') as stream:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                stream.add(path, arcname='InitialMaterials/' + path.relative_to(root).as_posix(), recursive=False)
    digest = sha(output)
    (out / 'InitialMaterials.sha256').write_text(digest + '  ' + output.name + '\n', encoding='utf-8')
    print('NUMERICAL_REPLAY: PASS_FIXED_POINT_HEX_REPLAY implementation=PYTHON_STDLIB_SCALAR ff1_cases=15 encoder_layers=12', flush=True)
    print('FLOAT_PARAMETERS_INCLUDED: PASS files=' + str(len(parameter_sha256)) + ' original_sha256=matched', flush=True)
    print('PREVIOUS_CANDIDATE_UNCHANGED: PASS', flush=True)
    print('INITIAL_MATERIAL_ARCHIVE:', output, 'bytes=' + str(output.stat().st_size), 'sha256=' + digest, flush=True)
    print('RESULT: INITIAL_CANDIDATE_NUMERICAL_REPLAY_RECOVERED; power/boundary/official accuracy/final acceptance pending', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--scalar', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--numerical', type=Path, required=True)
    args = parser.parse_args()
    recover(args.source.resolve(), args.out.resolve(), args.scalar.resolve(), args.source_sha256, args.numerical.resolve())
