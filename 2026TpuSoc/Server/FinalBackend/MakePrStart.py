"""Create the immutable inbound-only ICC2 reference-library/import entry."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parts = ['''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_icc2_start_20261108_XXXXXX")
mkdir -p "$work/tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: ICC2_ENTRY_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: real RVT/private SRAM NDM preparation and frozen accelerator ICC2 import/initial floorplan'
echo 'SCOPE: accelerator + 56 private SRAM macros; CPU/shared TCM excluded; no placement/CTS/route'
echo 'CONFIG: RVT 8lm_1tm trial; original TT DB/SDC; RC layer map not configured; no timing signoff'
echo 'LIMIT: total 35min; Library Manager 10min/library; ICC2 10min; caps are not runtime promises'
''']
    files = {name: HERE / name for name in ('PrStart.py', 'LefVariants.py', 'PrCommon.tcl', 'PrLibrary.tcl', 'PrImport.tcl',
                                           'Formal.py', 'Preflight.py')}
    files.update({name: HERE.parent / 'SystemBackend' / name for name in ('InitialMaterials.py', 'StageWatch.py')})
    for index, (name, path) in enumerate(files.items()):
        data = path.read_bytes().replace(b'\r\n', b'\n')
        encoded = base64.b64encode(gzip.compress(data, mtime=0)).decode()
        digest = hashlib.sha256(data).hexdigest()
        marker = 'TPUSOC_PR_FILE_' + str(index)
        parts.append('python3 - "$work/tools/' + name + '" <<\'' + marker + "'\n" +
                     'import base64,gzip,hashlib,sys\nfrom pathlib import Path\n' +
                     'data=gzip.decompress(base64.b64decode("' + encoded + '"))\n' +
                     'assert hashlib.sha256(data).hexdigest()=="' + digest + '"\n' +
                     'Path(sys.argv[1]).write_bytes(data)\n' + marker + '\n')
    parts.append('''export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$work/tools"
if ! python3 -B -u "$work/tools/StageWatch.py" --label icc2_library_import_floorplan --limit 2100 --log "$work/pr_runner.log" --cwd "$work" -- \\
    python3 -B -u "$work/tools/PrStart.py" "$work"; then
    tail -n 45 "$work/pr_runner.log"; exit 1
fi
tail -n 70 "$work/pr_runner.log"
echo "WORK_DIR: $work"
''')
    data = ''.join(parts).encode()
    path = ROOT / 'workspace/Server/tpusoc_icc2_start_20261108_v4.sh'
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Refusing to overwrite immutable PR entry')
    path.write_bytes(data)
    print('ARTIFACT', path, 'BYTES', len(data), 'SHA256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
