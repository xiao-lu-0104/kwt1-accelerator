"""Freeze 707cd7f inputs; never execute or overwrite a historical launcher."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FRONT = ROOT.parent / '2026TpuSoc_frontend_20261110_707cd7f'
REV = '707cd7f4a0a4d416d11bac71112980079e0a9d34'
OLD = 'c03eb048481b7d271dba54e518092c2eb9aa528f'
RTL = ('TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer '
       'TpuMatmul TpuGelu TpuVector TpuDma TpuTop TpuNice').split()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if subprocess.check_output(['git', '-C', str(FRONT), 'rev-parse', 'HEAD']).decode().strip() != REV:
        raise ValueError('Frontend HEAD mismatch')
    if subprocess.check_output(['git', '-C', str(FRONT), 'status', '--porcelain']).strip():
        raise ValueError('Frontend worktree must remain clean')
    files, origins = {}, {}
    for name in RTL:
        path = 'Rtl/' + name + '.sv'
        data = subprocess.check_output(['git', '-C', str(FRONT), 'show', REV + ':' + path])
        if data.replace(b'\r\n', b'\n') != (FRONT / path).read_bytes().replace(b'\r\n', b'\n'):
            raise ValueError('Worktree/source mismatch: ' + path)
        files['source/' + name + '.sv'] = data.replace(b'\r\n', b'\n')
        origins[path] = {'commit': REV, 'git_bytes_sha256': digest(data)}
    for path in ('Rtl/TpuIcb.sv', 'Backend/e203_subsys_nice_core.sv', 'Server/Backend/SpFoundry.sv'):
        data = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
        files['source/' + Path(path).name] = data
        origins[path] = {'local_integration_sha256': digest(data)}
    names = [n + '.sv' for n in RTL] + ['TpuIcb.sv', 'e203_subsys_nice_core.sv', 'SpFoundry.sv']
    files['source/Sources.tcl'] = ('set Sources {}\nforeach Name {' + ' '.join(names) +
        '} {lappend Sources [file join $::env(TPU_SHARED_SOURCE) $Name]}\n').encode()
    for src, dst in [
        (HERE / 'Run.tcl', 'Run.tcl'), (HERE / 'Run.sh', 'Run.sh'), (HERE / 'Probe.py', 'Probe.py'),
        (ROOT / 'Server/SharedAsic/Constraints.tcl', 'Constraints.tcl'),
        (ROOT / 'Server/SingleClock/HoldPolicy.tcl', 'HoldPolicy.tcl'),
        (ROOT / 'Server/Backend/AsicCommon.tcl', 'AsicCommon.tcl'),
        (ROOT / 'Server/Backend/CompileSpLib.tcl', 'CompileSpLib.tcl'),
        (ROOT / 'Server/Backend/VerifyMacro.py', 'VerifyMacro.py'),
        (ROOT / 'Server/SystemBackend/StageWatch.py', 'StageWatch.py')]:
        files['tools/' + dst] = src.read_bytes().replace(b'\r\n', b'\n')
    files['SourceProvenance.json'] = (json.dumps(dict(frontend_revision=REV, baseline=OLD,
        top='e203_subsys_nice_core', expected_private_macros=56,
        macro_basis='unchanged TpuSram; nonlegacy Regions=7, eight 1024x16 banks each',
        scope='accelerator/NICE/DMA/ICB/private112KiB; no CPU or shared TCM',
        qualification='native DC/function/equivalence not yet run', source_origins=origins), indent=2) + '\n').encode()
    for args, name in [(['diff', '--stat', OLD, REV], 'GitDiffStat.txt'),
                       (['diff', OLD, REV], 'GitDiff.patch'),
                       (['log', '--format=fuller', OLD + '..' + REV], 'GitCommits.txt')]:
        files[name] = subprocess.check_output(['git', '-C', str(FRONT)] + args)
    files['MANIFEST.sha256'] = ''.join(digest(data) + '  ' + name + '\n'
        for name, data in sorted(files.items())).encode()
    output = ROOT / 'workspace/Server/tpusoc_frontend_20261110_707cd7f_v1.sh'
    if output.exists():
        raise ValueError('Frozen entry exists; create another version')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(data), 0o644, 1794268800
            archive.addfile(item, io.BytesIO(data))
    packed = buffer.getvalue()
    shell = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_frontend_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'FRONTEND_707CD7F_PAYLOAD'
''' + base64.encodebytes(packed).decode() + '''FRONTEND_707CD7F_PAYLOAD
echo "''' + digest(packed) + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c MANIFEST.sha256
python3 -u tools/Probe.py "$work" | tee probe.log
echo "PROBE_ONLY_COMPLETE: no EDA job started or stopped"
echo "NEXT_DC_COMMAND: bash '$work/tools/Run.sh' '$work'"
'''
    output.write_bytes(shell.encode())
    print(output)
    print('BYTES', output.stat().st_size)
    print('SHA256', digest(output.read_bytes()))


if __name__ == '__main__':
    main()
