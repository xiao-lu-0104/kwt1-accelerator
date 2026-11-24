"""Prepare v2 for use only after the currently running recovery has ended."""
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


def files_for_build():
    original = (HERE / 'Resume.tcl').read_text()
    old = '''    set Frozen ""
    foreach_in_collection Cell [get_cells -hierarchical] {
        set Name [get_object_name $Cell]
        if {![InSram $Name] && ![SramAncestor $Name]} {
            set Frozen [add_to_collection $Frozen $Cell]
        }
    }
'''
    if original.count(old) != 1:
        raise ValueError('Reviewed v1 freeze block changed')
    tcl = original.replace(old, '    source [file join $Tools FastFreeze.tcl]\n    set Frozen [FastFrozenCollection]\n')
    tcl = tcl.replace('    set_fix_hold [get_clocks CoreClock]\n',
        '    puts "HOLD_STAGE: dont_touch_complete"\n    set_fix_hold [get_clocks CoreClock]\n    puts "HOLD_STAGE: compile_hold_start"\n')
    tcl = tcl.replace('    set Repaired 1\n', '    puts "HOLD_STAGE: compile_hold_complete"\n    set Repaired 1\n')
    runner = (HERE / 'Resume.py').read_text()
    marker = '    paths, libraries = verify(run, config[\'original_manifest_sha256\'])\n'
    guard = '''    # Do not overlap the existing recovery or discard a newer candidate.
    listing = subprocess.check_output(['ps', '-u', str(os.getuid()), '-o', 'args='], universal_newlines=True)
    for line in listing.splitlines():
        if 'dc_shell' in line and '/soc/tpusoc_hold_recovery_20261110_707cd7f_' in line and '/tools/Resume.tcl' in line:
            raise ValueError('Another 707cd7f recovery DC is still running; leave it untouched')
    for previous in (Path.home() / 'soc').glob('tpusoc_hold_recovery_20261110_707cd7f_*'):
        candidate = previous / 'mapped/candidate.ddc'
        if previous.resolve() != out and candidate.is_file() and candidate.stat().st_size:
            raise ValueError('An earlier recovery has a candidate; review it instead of restarting baseline: ' + str(previous))
'''
    if runner.count(marker) != 1:
        raise ValueError('Reviewed v1 runner changed')
    runner = runner.replace(marker, guard + marker)
    files = {'tools/Resume.tcl': tcl.encode(), 'tools/Resume.py': runner.encode(),
             'tools/FastFreeze.tcl': (HERE / 'FastFreeze.tcl').read_bytes()}
    for path in (ROOT / 'Server/SystemBackend/StageWatch.py', ROOT / 'Server/Backend/AsicCommon.tcl',
                 ROOT / 'Server/SingleClock/HoldPolicy.tcl'):
        files['tools/' + path.name] = path.read_bytes().replace(b'\r\n', b'\n')
    files['RecoveryConfig.json'] = (json.dumps({'source_commit': '707cd7f4a0a4d416d11bac71112980079e0a9d34',
        'original_run': 'tpusoc_frontend_20261110_707cd7f_ZKpdeM',
        'original_manifest_sha256': sha((ROOT / 'Doc/DCScripts_20261110_707cd7f/MANIFEST.sha256').read_bytes()),
        'version': 2, 'limit_seconds': 7200, 'freeze_scope': 'identical predicate; native bulk collection with independent count/membership checks'}, indent=2) + '\n').encode()
    return files


def main():
    files = files_for_build()
    files['PACKAGE.sha256'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as archive:
        for n, b in sorted(files.items()):
            m = tarfile.TarInfo(n)
            m.size, m.mode, m.mtime = len(b), 0o644, 1704067200
            archive.addfile(m, io.BytesIO(b))
    data = buf.getvalue()
    shell = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_hold_recovery_20261110_707cd7f_v2_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'FAST_HOLD_RECOVERY_707CD7F'
''' + base64.encodebytes(data).decode() + '''FAST_HOLD_RECOVERY_707CD7F
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
    output = ROOT / 'workspace/Server/tpusoc_hold_recovery_20261110_707cd7f_v2.sh'
    if output.exists():
        raise ValueError('Never overwrite a frozen artifact')
    output.write_bytes(shell.encode())
    print(output.name, output.stat().st_size, sha(output.read_bytes()))


if __name__ == '__main__':
    main()
