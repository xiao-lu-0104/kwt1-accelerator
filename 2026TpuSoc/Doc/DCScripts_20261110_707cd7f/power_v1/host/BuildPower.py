"""New current-system tasks/SAIF/power package; no old SAIF or old launcher execution."""
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
    firmware = ROOT / 'workspace/Checks/PowerFirmware_20261110_707cd7f_v1'
    proof = json.loads((firmware / 'BuildEvidence/FirmwareEvidence.json').read_text())
    if proof['frontend_revision'] != '707cd7f4a0a4d416d11bac71112980079e0a9d34':
        raise ValueError('Firmware source mismatch')
    for name, h in proof['sha256'].items():
        if sha((firmware / name).read_bytes()) != h:
            raise ValueError('Firmware evidence changed: ' + name)
    tasks = (ROOT / 'Server/RefreshPower/Tasks.py').read_text()
    a, b = tasks.index('def prepare(out):'), tasks.index('def validate(out,name):')
    tasks = tasks[:a] + 'def prepare(out):\n    from PreparePower import prepare_current\n    prepare_current(out)\n\n\n' + tasks[b:]
    runner = (ROOT / 'Server/RefreshPower/Run.py').read_text()
    runner = runner.replace("run('prepare_current_tasks',300,", "run('prepare_current_tasks',900,")
    runner = runner.replace("run('compile_current_tasks',900,", "run('compile_current_tasks',1800,")
    runner = runner.replace("1200 if name=='ff1' else 2700", "2400 if name=='ff1' else 5400")
    runner = runner.replace("run(stage,1000,", "run(stage,4200,")
    runner = runner.replace('new 20261109 system', 'new 707cd7f 20261110 system')
    power = (ROOT / 'Server/RefreshPower/Power.py').read_text().replace('tool_root=None,limit=900', 'tool_root=None,limit=3600')
    tcl = (ROOT / 'Server/RefreshPower/Power.tcl').read_text()
    a = tcl.index('    foreach Key $Keys {set Groups($Key) ""}')
    b = tcl.index('    set F [open groups.tsv w]', a)
    tcl = tcl[:a] + '    source [file join $::env(NEW_POWER_TOOLS) PowerGroups.tcl]\n    MakePowerGroups\n' + tcl[b:]
    files = {'tools/Tasks.py': tasks.encode(), 'tools/Run.py': runner.encode(), 'tools/Power.py': power.encode(), 'tools/Power.tcl': tcl.encode(),
             'tools/Guards.py': (HERE / 'PowerGuards.py').read_bytes()}
    for path in (HERE / 'PreparePower.py', HERE / 'SystemFlow.py', HERE / 'PowerGroups.tcl', ROOT / 'Server/RefreshDc/Review.py',
                 ROOT / 'Server/SharedAsic/PrepareInventory.py', ROOT / 'Server/SharedAsic/ReadProbe.py', ROOT / 'Server/SharedAsic/TaskActivity.sv',
                 ROOT / 'Server/SystemBackend/SystemTasks.py', ROOT / 'Server/SystemBackend/Prepare.py', ROOT / 'Server/SystemBackend/StageWatch.py',
                 ROOT / 'Server/SystemBackend/TcmInitializer.sv', ROOT / 'Server/SystemBackend/AreaBreakdown.tcl',
                 ROOT / 'Server/SystemBackend/PowerCoverage.py', ROOT / 'Server/Backend/AsicCommon.tcl'):
        files['tools/' + path.name] = path.read_bytes().replace(b'\r\n', b'\n')
    for path in firmware.rglob('*'):
        if path.is_file():
            files['firmware/' + path.relative_to(firmware).as_posix()] = path.read_bytes()
    files['PowerConfig.json'] = (json.dumps({'source_commit': proof['frontend_revision'],
        'system_package_sha256': sha((ROOT / 'Doc/DCScripts_20261110_707cd7f/system_v1/PACKAGE.sha256').read_bytes()),
        'tasks': ['ff1_normal_single', 'encoder_single_layer'], 'old_saif_reuse': False,
        'limits_seconds': {'prepare': 900, 'compile': 1800, 'ff1_sim': 2400, 'encoder_sim': 5400, 'power_native_per_task': 3600, 'power_outer_per_task': 4200}}, indent=2) + '\n').encode()
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
    data = buf.getvalue()
    shell = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_task_power_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'TASK_POWER_707CD7F_PAYLOAD'
''' + base64.encodebytes(data).decode() + '''TASK_POWER_707CD7F_PAYLOAD
echo "''' + sha(data) + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "TASK_POWER_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
echo 'SOURCE: 707cd7f new system DDC + new exact-driver firmware + fresh full-system SAIF; no old SAIF reuse'
echo 'MODE: CPU RTL + frozen current accelerator gates + real120 macros; zero delay, no SDF; task validity and X checks required'
python3 -u tools/Run.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    output = ROOT / 'workspace/Server/tpusoc_task_power_20261110_707cd7f_v1.sh'
    if output.exists():
        raise ValueError('Never overwrite frozen power entry')
    output.write_bytes(shell.encode())
    print(output.name, output.stat().st_size, sha(output.read_bytes()))


if __name__ == '__main__':
    main()
