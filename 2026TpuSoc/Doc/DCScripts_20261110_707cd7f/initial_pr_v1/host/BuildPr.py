"""Prepare an isolated new placement package using inspected reusable helpers."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def build_files():
    helpers = (ROOT / 'Server/RefreshPr/Run.py').read_text().split('def main(out):', 1)[0]
    helpers = helpers.replace('"""Fresh 1109 full-system ICC2 import and initial placement, reusing only physical libraries."""',
                              '"""Inspected helper functions only; no historical design runner included."""')
    selection = (HERE / 'PreparePower.py').read_text()
    selection = selection[selection.index('def select_system('):selection.index('def prepare_current(')]
    selection = 'import json\nfrom pathlib import Path\nfrom SystemFlow import REV,sha,verify_manifest,check_hashes,validate_system\n\n' + selection
    place = (ROOT / 'Server/RefreshPr/Place.tcl').read_text()
    place = place.replace('# Only the 1109 e203_cpu_top netlist and SDC are read as a design.', '# Only the current pinned 707cd7f system netlist and SDC are imported as a design.')
    for a, b in [('NEW_1109_E203_CPU_TOP_PRIVATE56_SHARED64', 'NEW_707CD7F_E203_CPU_TOP_PRIVATE56_SHARED64'),
                 ('read_1109_verilog', 'read_current_verilog'), ('link_1109', 'link_current'),
                 ('read_1109_sdc', 'read_current_sdc'), ('placed_1109.def', 'placed_707cd7f.def')]:
        place = place.replace(a, b)
    files = {'tools/PrHelpers.py': helpers.encode(), 'tools/SelectSystem.py': selection.encode(), 'tools/Place.tcl': place.encode()}
    for p in (HERE / 'PrFlow.py', HERE / 'SystemFlow.py', ROOT / 'Server/SystemBackend/StageWatch.py',
              ROOT / 'Server/FinalBackend/Preflight.py', ROOT / 'Server/FinalBackend/PrCommon.tcl'):
        files['tools/' + p.name] = p.read_bytes().replace(b'\r\n', b'\n')
    files['Config.json'] = (json.dumps({'source_commit': '707cd7f4a0a4d416d11bac71112980079e0a9d34',
        'system_package_sha256': sha((ROOT / 'Doc/DCScripts_20261110_707cd7f/system_v1/PACKAGE.sha256').read_bytes()),
        'power_package_sha256': sha((ROOT / 'Doc/DCScripts_20261110_707cd7f/power_v1/PACKAGE.sha256').read_bytes()),
        'scope': 'current full system ICC2 import/floorplan/initial placement only; not routed', 'limit_seconds': 3600}, indent=2) + '\n').encode()
    return files


def main():
    files = build_files()
    files['PACKAGE.sha256'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as archive:
        for n, b in sorted(files.items()):
            m = tarfile.TarInfo(n); m.size, m.mode, m.mtime = len(b), 0o644, 1704067200
            archive.addfile(m, io.BytesIO(b))
    data = buf.getvalue()
    entry = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_initial_pr_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'INITIAL_PR_707CD7F_PAYLOAD'
''' + base64.encodebytes(data).decode() + '''INITIAL_PR_707CD7F_PAYLOAD
echo "''' + sha(data) + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "INITIAL_PR_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/PrFlow.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    output = ROOT / 'workspace/Server/tpusoc_initial_pr_20261110_707cd7f_v1.sh'
    if output.exists():
        raise ValueError('Never overwrite frozen PR entry')
    output.write_bytes(entry.encode())
    print(output.name, output.stat().st_size, sha(output.read_bytes()))


if __name__ == '__main__':
    main()
