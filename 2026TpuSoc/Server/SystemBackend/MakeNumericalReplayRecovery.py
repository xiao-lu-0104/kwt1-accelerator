"""Build an FTP-uploadable, standard-library-only candidate replay recovery."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE_SHA = '5d44fec1b2e8a02861e2acd8c0ec4f36ea47d562b13331cca3ce8c2a553c7224'


def main():
    parts = ['''#!/usr/bin/env bash
set -euo pipefail
source_run=$(python3 - "$HOME/soc" <<'TPUSOC_FIND_INITIAL_CANDIDATE'
from pathlib import Path
import sys
for path in sorted(Path(sys.argv[1]).glob('tpusoc_initial_materials_20261107_*'),key=lambda p:p.stat().st_mtime,reverse=True):
    proof=path/'InitialMaterials.sha256'
    if proof.is_file() and proof.read_text().split()[0]=='SOURCE_DIGEST':
        print(path); break
else: raise SystemExit('ERROR: the successfully merged original candidate is required')
TPUSOC_FIND_INITIAL_CANDIDATE
)
work=$(mktemp -d "$HOME/soc/tpusoc_numerical_replay_20261107_XXXXXX")
mkdir -p "$work/tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: NUMERICAL_REPLAY_RECOVERY_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo "PREVIOUS_CANDIDATE: $source_run"
echo 'MODE: standard-library scalar replay and new candidate archive; no NumPy/install/network/DC/VCS'
echo 'LIMIT: verify/replay/copy/archive 15min; replay 5min cap; original candidate preserved'
'''.replace('SOURCE_DIGEST', SOURCE_SHA)]
    files = {name: (HERE / name).read_bytes().replace(b'\r\n', b'\n') for name in
             ('RecoverNumericalReplay.py', 'InitialMaterials.py', 'CheckSharedHexScalar.py', 'StageWatch.py')}
    numerical = ROOT / 'workspace/Checks/InitialNumerics_20261106_hrz58ess/NumericalMaterial.partial.tar.gz'
    files['NumericalMaterial.partial.tar.gz'] = numerical.read_bytes()
    if hashlib.sha256(files['NumericalMaterial.partial.tar.gz']).hexdigest() != 'd6d63bb158523bb3423c735f6d793a54e613c29b4bd29c253ca3a7656ffb3b1b':
        raise ValueError('Original numerical archive changed')
    for index, (name, data) in enumerate(files.items()):
        digest = hashlib.sha256(data).hexdigest()
        encoded = base64.b64encode(gzip.compress(data, mtime=0)).decode()
        marker = 'TPUSOC_STDLIB_RECOVERY_' + str(index)
        parts.append('python3 - "$work/tools/' + name + '" <<\'' + marker + "'\n" +
            'import base64,gzip,hashlib,sys\nfrom pathlib import Path\n' +
            'data=gzip.decompress(base64.b64decode("' + encoded + '"))\n' +
            'assert hashlib.sha256(data).hexdigest()=="' + digest + '"\n' +
            'Path(sys.argv[1]).write_bytes(data)\n' + marker + '\n')
    parts.append('''export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$work/tools"
if ! python3 -B -u "$work/tools/StageWatch.py" --label stdlib_numerical_replay --limit 900 --log "$work/replay_recovery.log" --cwd "$work" -- \\
    python3 -B -u "$work/tools/RecoverNumericalReplay.py" "$work" --source "$source_run" --scalar "$work/tools/CheckSharedHexScalar.py" --source-sha256 SOURCE_DIGEST --numerical "$work/tools/NumericalMaterial.partial.tar.gz"; then
    tail -n 25 "$work/replay_recovery.log"; exit 1
fi
cat "$work/replay_recovery.log"
echo "WORK_DIR: $work"
'''.replace('SOURCE_DIGEST', SOURCE_SHA))
    data = ''.join(parts).encode()
    output = ROOT / 'workspace/Server/tpusoc_numerical_replay_20261107_v1.sh'
    if output.exists() and output.read_bytes() != data:
        raise ValueError('Refusing to replace versioned artifact')
    output.write_bytes(data)
    print('ARTIFACT', output, 'BYTES', len(data), 'SHA256', hashlib.sha256(data).hexdigest())
    print('TRANSFER: FTP upload only; do not paste the payload in VNC')


if __name__ == '__main__':
    main()
