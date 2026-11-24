"""Package the initial coarse placement stage; no outbound transfer."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parts = ['''#!/usr/bin/env bash
set -euo pipefail
source_run="$HOME/soc/tpusoc_icc2_start_20261108_mTq1LE"
[[ -s "$source_run/PrSummary.json" ]] || { echo "ERROR: Missing successful import $source_run"; exit 2; }
work=$(mktemp -d "$HOME/soc/tpusoc_icc2_coarse_20261108_XXXXXX")
mkdir -p "$work/tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: COARSE_ENTRY_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: isolated copies of successful import; initial coarse placement and macro geometry review'
echo 'LIMIT: total 25min; native ICC2 20min; caps are not runtime promises'
''']
    files = {name: HERE / name for name in ('PrCoarse.py', 'PrCoarse.tcl', 'PrCommon.tcl', 'PrStart.py', 'Formal.py', 'Preflight.py')}
    files['StageWatch.py'] = HERE.parent / 'SystemBackend/StageWatch.py'
    for index, (name, path) in enumerate(files.items()):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        digest = hashlib.sha256(data).hexdigest()
        encoded = base64.b64encode(gzip.compress(data, mtime=0)).decode()
        marker = 'TPUSOC_COARSE_' + str(index)
        parts.append('python3 - "$work/tools/' + name + '" <<\'' + marker + "'\n" +
                     'import base64,gzip,hashlib,sys\nfrom pathlib import Path\n' +
                     'data=gzip.decompress(base64.b64decode("' + encoded + '"))\n' +
                     'assert hashlib.sha256(data).hexdigest()=="' + digest + '"\n' +
                     'Path(sys.argv[1]).write_bytes(data)\n' + marker + '\n')
    parts.append('''export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$work/tools"
if ! python3 -B -u "$work/tools/StageWatch.py" --label icc2_initial_coarse --limit 1500 --log "$work/coarse_runner.log" --cwd "$work" -- \\
    python3 -B -u "$work/tools/PrCoarse.py" "$work" --source "$source_run"; then
    tail -n 40 "$work/coarse_runner.log"; exit 1
fi
tail -n 55 "$work/coarse_runner.log"
echo "WORK_DIR: $work"
''')
    data = ''.join(parts).encode()
    path = ROOT / 'workspace/Server/tpusoc_icc2_coarse_20261108_v1.sh'
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Refusing immutable coarse entry overwrite')
    path.write_bytes(data)
    print('ARTIFACT', path, 'BYTES', len(data), 'SHA256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
