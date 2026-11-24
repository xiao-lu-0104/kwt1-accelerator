"""Verify a relocated initial candidate without changing its files or installing tools."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def verify(root):
    entries = set()
    for line in (root / 'MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        path = root / name
        if name in entries or root not in path.resolve().parents or path.is_symlink():
            raise ValueError('Unsafe/duplicate manifest path: ' + name)
        value = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                value.update(chunk)
        if value.hexdigest() != digest:
            raise ValueError('Checksum mismatch: ' + name)
        entries.add(name)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*')
              if p.is_file() and p != root / 'MANIFEST.sha256'}
    if actual != entries or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Files differ from the complete manifest')
    print('INITIAL_MATERIAL_INTEGRITY: PASS files=' + str(len(entries)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    verify(root)
    review = json.loads((root / 'ReviewStatus.json').read_text(encoding='utf-8'))
    print('CANDIDATE_STATUS:', review['status'], flush=True)
    for issue in review['remaining']:
        print('REMAINING:', issue, flush=True)
    if args.replay:
        with tempfile.TemporaryDirectory(prefix='tpusoc_numerical_replay_') as directory:
            return subprocess.run([sys.executable, '-B', str(root / 'Reproduce/CheckSharedHex.py'),
                '--vectors', str(root / 'Project/Vectors'), '--model', str(root / 'Project/Model'),
                '--out', str(Path(directory) / 'Result.json')], cwd=directory, timeout=300).returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
