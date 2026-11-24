"""Create a versioned FTP-uploadable formal/physical prerequisite inspection entry."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE_SHA = '63104eac90eb30e02dd1f8df504fea4360fbdb8a73fb8945ebb222ee1186bbda'


def main():
    parts = ['''#!/usr/bin/env bash
set -euo pipefail
source_run=$(python3 - "$HOME/soc" <<'TPUSOC_FINAL_PREFLIGHT_SOURCE'
from pathlib import Path
import sys
for path in sorted(Path(sys.argv[1]).glob('tpusoc_numerical_replay_20261107_*'),key=lambda p:p.stat().st_mtime,reverse=True):
    proof=path/'InitialMaterials.sha256'
    if proof.is_file() and proof.read_text().split()[0]=='SOURCE_DIGEST':
        print(path); break
else: raise SystemExit('ERROR: the completed numerical-replay candidate is required')
TPUSOC_FINAL_PREFLIGHT_SOURCE
)
previous_run=$(python3 - "$HOME/soc" <<'TPUSOC_FINAL_PREFLIGHT_RESUME'
from pathlib import Path
import hashlib,sys
for path in sorted(Path(sys.argv[1]).glob('tpusoc_final_preflight_20261108_*'),key=lambda p:p.stat().st_mtime,reverse=True):
    script=path/'tools/Preflight.py'
    if script.is_file() and (path/'FrozenInputs.json').is_file() and (path/'fm_commands.log').is_file():
        if hashlib.sha256(script.read_bytes()).hexdigest()=='c7e4863b4cd919d9bb1a92e393b1dea1e92e2ec63c2f78b18866c8d22cdb19b6':
            print(path); break
else: raise SystemExit('ERROR: prior v3 documentation logs are required for recovery')
TPUSOC_FINAL_PREFLIGHT_RESUME
)
work=$(mktemp -d "$HOME/soc/tpusoc_final_preflight_20261108_XXXXXX")
mkdir -p "$work/tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: FINAL_BACKEND_PREFLIGHT_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo "SOURCE_CANDIDATE: $source_run"
echo "RECOVERY_SOURCE: $previous_run"
echo 'MODE: frozen-input verification; tool help/session and bounded PDK/LEF/RC inventory only'
echo 'LIMIT: total 5min; reuse v3 help logs; scan 35sec/root; LEF 12sec/file with 90sec combined cap'
echo 'SCOPE: no synthesis, equivalence match/verify, placement, CTS or route in this inspection'
'''.replace('SOURCE_DIGEST', SOURCE_SHA)]
    files = {'Preflight.py': HERE / 'Preflight.py',
             'InitialMaterials.py': HERE.parent / 'SystemBackend/InitialMaterials.py',
             'StageWatch.py': HERE.parent / 'SystemBackend/StageWatch.py'}
    for index, (name, path) in enumerate(files.items()):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        encoded = base64.b64encode(gzip.compress(data, mtime=0)).decode()
        digest = hashlib.sha256(data).hexdigest()
        marker = 'TPUSOC_FINAL_PREFLIGHT_' + str(index)
        parts.append('python3 - "$work/tools/' + name + '" <<\'' + marker + "'\n" +
            'import base64,gzip,hashlib,sys\nfrom pathlib import Path\n' +
            'data=gzip.decompress(base64.b64decode("' + encoded + '"))\n' +
            'assert hashlib.sha256(data).hexdigest()=="' + digest + '"\n' +
            'Path(sys.argv[1]).write_bytes(data)\n' + marker + '\n')
    parts.append('''export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$work/tools"
if ! python3 -B -u "$work/tools/StageWatch.py" --label final_backend_preflight --limit 300 --log "$work/preflight.log" --cwd "$work" -- \\
    python3 -B -u "$work/tools/Preflight.py" "$work" --source "$source_run" --resume "$previous_run"; then
    tail -n 25 "$work/preflight.log"; exit 1
fi
tail -n 24 "$work/preflight.log"
echo "WORK_DIR: $work"
''')
    data = ''.join(parts).encode()
    output = ROOT / 'workspace/Server/tpusoc_final_preflight_20261108_v4.sh'
    if output.exists() and output.read_bytes() != data:
        raise ValueError('Refusing to replace versioned artifact')
    output.write_bytes(data)
    print('ARTIFACT', output, 'BYTES', len(data), 'SHA256', hashlib.sha256(data).hexdigest())
    print('TRANSFER: FTP upload; only a short launcher command goes in VNC')


if __name__ == '__main__':
    main()
