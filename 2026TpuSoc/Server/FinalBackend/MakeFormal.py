"""Package a bounded actual accelerator Formality attempt for inbound-only FTP."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parts = ['''#!/usr/bin/env bash
set -euo pipefail
preflight=$(python3 - "$HOME/soc" <<'TPUSOC_FORMAL_SOURCE'
from pathlib import Path
import json,sys
for path in sorted(Path(sys.argv[1]).glob('tpusoc_final_preflight_20261108_*'),key=lambda p:p.stat().st_mtime,reverse=True):
    proof=path/'BackendPreflight.json'
    if not proof.is_file(): continue
    record=json.loads(proof.read_text())
    if record.get('status')=='FINAL_BACKEND_PREFLIGHT_COLLECTED' and record.get('tools',{}).get('fm_shell',{}).get('executable'):
        print(path); break
else: raise SystemExit('ERROR: completed Formality/PDK preflight required')
TPUSOC_FORMAL_SOURCE
)
work=$(mktemp -d "$HOME/soc/tpusoc_formal_accelerator_20261108_XXXXXX")
mkdir -p "$work/tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: FORMAL_ENTRY_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo "PREFLIGHT_SOURCE: $preflight"
echo 'MODE: exact frozen RTL/netlist/libraries; provenance-check original accelerator SVF and load before design; automatic setup disabled'
echo 'LIMITATION: array-index reachability remains unproved; no compare points, reset or state are waived'
echo 'LIMIT: total 25min; actual FM process 20min; ICC2 documentation 75sec; caps are not runtime promises'
echo 'SCOPE: NICE/TPU/DMA/ICB/private SRAM boundary; no CPU/shared-TCM proof, placement or routing in this stage'
''']
    files = {'Formal.py': HERE / 'Formal.py', 'Formal.tcl': HERE / 'Formal.tcl',
             'Preflight.py': HERE / 'Preflight.py',
             'InitialMaterials.py': HERE.parent / 'SystemBackend/InitialMaterials.py',
             'StageWatch.py': HERE.parent / 'SystemBackend/StageWatch.py'}
    for index, (name, path) in enumerate(files.items()):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        encoded = base64.b64encode(gzip.compress(data, mtime=0)).decode()
        digest = hashlib.sha256(data).hexdigest()
        marker = 'TPUSOC_FORMAL_FILE_' + str(index)
        parts.append('python3 - "$work/tools/' + name + '" <<\'' + marker + "'\n" +
                     'import base64,gzip,hashlib,sys\nfrom pathlib import Path\n' +
                     'data=gzip.decompress(base64.b64decode("' + encoded + '"))\n' +
                     'assert hashlib.sha256(data).hexdigest()=="' + digest + '"\n' +
                     'Path(sys.argv[1]).write_bytes(data)\n' + marker + '\n')
    parts.append('''export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$work/tools"
if ! python3 -B -u "$work/tools/StageWatch.py" --label formal_accelerator_collection --limit 1500 --log "$work/formal_runner.log" --cwd "$work" -- \\
    python3 -B -u "$work/tools/Formal.py" "$work" --preflight "$preflight"; then
    tail -n 30 "$work/formal_runner.log"; exit 1
fi
tail -n 100 "$work/formal_runner.log"
echo "WORK_DIR: $work"
''')
    data = ''.join(parts).encode()
    path = ROOT / 'workspace/Server/tpusoc_formal_accelerator_20261108_v5.sh'
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Refusing to overwrite an immutable versioned entry')
    path.write_bytes(data)
    print('ARTIFACT', path, 'BYTES', len(data), 'SHA256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
