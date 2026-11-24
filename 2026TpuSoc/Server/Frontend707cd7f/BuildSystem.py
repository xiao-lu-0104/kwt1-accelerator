"""Freeze the new review/FM/system pipeline against this exact accelerator."""
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


def build_files():
    system = (ROOT / 'Server/RefreshDc/System.tcl').read_text()
    target = 'foreach {Key Value} [list TOP e203_cpu_top PERIOD_NS 6.666667'
    if system.count(target) != 1:
        raise ValueError('Reviewed system Tcl changed')
    system = system.replace(target, 'foreach {Key Value} [list TOP e203_cpu_top SOURCE_ID 707cd7f4a0a4d416d11bac71112980079e0a9d34 PERIOD_NS 6.666667')
    system = system.replace('    if {$BudgetSignature ne [FrozenBudgetSignature candidate.sdc]}',
                            '    puts "SYSTEM_STAGE: candidate_saved"\n    if {$BudgetSignature ne [FrozenBudgetSignature candidate.sdc]}')
    files = {'tools/System.tcl': system.encode()}
    for path in (HERE / 'SystemFlow.py', ROOT / 'Server/RefreshDc/Equiv.tcl',
                 ROOT / 'Server/SystemBackend/StageWatch.py', ROOT / 'Server/SystemBackend/TcmMacro.sv',
                 ROOT / 'Server/SystemBackend/AreaBreakdown.tcl', ROOT / 'Server/Backend/AsicCommon.tcl'):
        files['tools/' + path.name] = path.read_bytes().replace(b'\r\n', b'\n')
    files['Config.json'] = (json.dumps({'source_commit': '707cd7f4a0a4d416d11bac71112980079e0a9d34',
        'accelerator_run': 'tpusoc_hold_recovery_20261110_707cd7f_Bwf2gR',
        'original_manifest_sha256': sha((ROOT / 'Doc/DCScripts_20261110_707cd7f/MANIFEST.sha256').read_bytes()),
        'accelerator_recovery_package_sha256': sha((ROOT / 'Doc/DCScripts_20261110_707cd7f/recovery_v1/PACKAGE.sha256').read_bytes()),
        'limits_seconds': {'hold_equivalence': 3600, 'system_dc': 7200}}, indent=2) + '\n').encode()
    return files


def main():
    files = build_files()
    files['PACKAGE.sha256'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as archive:
        for n, b in sorted(files.items()):
            m = tarfile.TarInfo(n)
            m.size, m.mode, m.mtime = len(b), 0o644, 1704067200
            archive.addfile(m, io.BytesIO(b))
    packed = buf.getvalue()
    shell = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_system_dc_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'SYSTEM_707CD7F_PAYLOAD'
''' + base64.encodebytes(packed).decode() + '''SYSTEM_707CD7F_PAYLOAD
echo "''' + sha(packed) + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "SYSTEM_FLOW_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/SystemFlow.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    output = ROOT / 'workspace/Server/tpusoc_system_dc_20261110_707cd7f_v1.sh'
    if output.exists():
        raise ValueError('Never overwrite frozen package')
    output.write_bytes(shell.encode())
    print(output.name, output.stat().st_size, sha(output.read_bytes()))


if __name__ == '__main__':
    main()
