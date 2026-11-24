"""Freeze a new baseline-only recovery package; do not mutate v1."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    old = ROOT / 'Doc/DCScripts_20261110_707cd7f/MANIFEST.sha256'
    files = {'RecoveryConfig.json': (json.dumps({'source_commit': '707cd7f4a0a4d416d11bac71112980079e0a9d34',
        'original_run': 'tpusoc_frontend_20261110_707cd7f_ZKpdeM',
        'original_manifest_sha256': sha(old.read_bytes()), 'limit_seconds': 7200}, indent=2) + '\n').encode()}
    for path in (HERE / 'Resume.py', HERE / 'Resume.tcl', ROOT / 'Server/SystemBackend/StageWatch.py',
                 ROOT / 'Server/Backend/AsicCommon.tcl', ROOT / 'Server/SingleClock/HoldPolicy.tcl'):
        files['tools/' + path.name] = path.read_bytes().replace(b'\r\n', b'\n')
    files['PACKAGE.sha256'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data in sorted(files.items()):
            m = tarfile.TarInfo(name)
            m.size, m.mode, m.mtime = len(data), 0o644, 1704067200
            archive.addfile(m, io.BytesIO(data))
    data = buffer.getvalue()
    shell = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_hold_recovery_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'HOLD_RECOVERY_707CD7F'
''' + base64.encodebytes(data).decode() + '''HOLD_RECOVERY_707CD7F
echo "''' + sha(data) + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "HOLD_RECOVERY_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/Resume.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    output = ROOT / 'workspace/Server/tpusoc_hold_recovery_20261110_707cd7f_v1.sh'
    if output.exists():
        raise ValueError('Refusing to overwrite frozen recovery')
    output.write_bytes(shell.encode())
    print(output.name, output.stat().st_size, sha(output.read_bytes()))


if __name__ == '__main__':
    main()
