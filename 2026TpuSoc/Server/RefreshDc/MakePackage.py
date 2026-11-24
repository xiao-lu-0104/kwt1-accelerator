"""Package pinned upstream RTL with the existing platform ICB wrapper for fresh DC."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FRONT = ROOT.parent / '2026TpuSoc_frontend_20261109'
REV = 'c03eb048481b7d271dba54e518092c2eb9aa528f'
RTL = ('TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer '
       'TpuMatmul TpuGelu TpuVector TpuDma TpuTop TpuNice').split()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build():
    if subprocess.check_output(['git', '-C', str(FRONT), 'rev-parse', 'HEAD']).decode().strip() != REV:
        raise ValueError('Unexpected frontend revision')
    files = {}
    origins = {}
    for name in RTL:
        relative = 'Rtl/' + name + '.sv'
        data = subprocess.check_output(['git', '-C', str(FRONT), 'show', REV + ':' + relative])
        if data.replace(b'\r\n', b'\n') != (FRONT / relative).read_bytes().replace(b'\r\n', b'\n'):
            raise ValueError('Frontend worktree changed: ' + relative)
        target = 'source/' + name + '.sv'
        files[target] = data.replace(b'\r\n', b'\n')
        origins[target] = {'revision': REV, 'path': relative, 'git_blob_bytes_sha256': sha(data)}
    for relative in ('Rtl/TpuIcb.sv', 'Backend/e203_subsys_nice_core.sv', 'Server/Backend/SpFoundry.sv'):
        target = 'source/' + Path(relative).name
        files[target] = (ROOT / relative).read_bytes().replace(b'\r\n', b'\n')
        origins[target] = {'local_integration_path': relative, 'sha256': sha(files[target])}
    names = [name + '.sv' for name in RTL] + ['TpuIcb.sv', 'e203_subsys_nice_core.sv', 'SpFoundry.sv']
    files['source/Sources.tcl'] = ('set Sources {}\nforeach Name {' + ' '.join(names) +
        '} {lappend Sources [file join $::env(TPU_SHARED_SOURCE) $Name]}\n').encode()
    for source, target in [
        (HERE / 'Run.tcl', 'Run.tcl'), (HERE / 'Run.sh', 'Run.sh'),
        (ROOT / 'Server/SharedAsic/Constraints.tcl', 'Constraints.tcl'),
        (ROOT / 'Server/SingleClock/HoldPolicy.tcl', 'HoldPolicy.tcl'),
        (ROOT / 'Server/Backend/AsicCommon.tcl', 'AsicCommon.tcl'),
        (ROOT / 'Server/Backend/CompileSpLib.tcl', 'CompileSpLib.tcl'),
        (ROOT / 'Server/Backend/VerifyMacro.py', 'VerifyMacro.py'),
        (ROOT / 'Server/SystemBackend/StageWatch.py', 'StageWatch.py')]:
        files['tools/' + target] = source.read_bytes().replace(b'\r\n', b'\n')
    files['SourceProvenance.json'] = (json.dumps({
        'frontend_revision': REV, 'source_origins': origins,
        'top': 'e203_subsys_nice_core', 'functional_status': 'NEW_COMBINATION_NOT_YET_QUALIFIED',
        'scope': 'NICE+TPU+DMA+ICB+56 private SRAM; CPU/shared TCM excluded',
        'upstream_validation': 'Doc/MemoryPipeline.md reports upstream tests; not reproduced here'
    }, indent=2) + '\n').encode()
    files['MANIFEST.sha256'] = ''.join(sha(data) + '  ' + name + '\n'
        for name, data in sorted(files.items())).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    packed = buffer.getvalue()
    encoded = base64.encodebytes(packed).decode()
    entry = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_refresh_dc_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'TPUSOC_REFRESH_PAYLOAD'
''' + encoded + '''TPUSOC_REFRESH_PAYLOAD
echo "''' + sha(packed) + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c MANIFEST.sha256
exec bash tools/Run.sh "$work"
'''
    output = ROOT / 'workspace/Server/tpusoc_refresh_dc_20261109_v1.sh'
    # Freeze the first artifact; gzip metadata may differ on a later build.
    if output.exists():
        raise ValueError('Versioned entry already exists; use a new version for changes')
    output.write_bytes(entry.encode())
    print('ARTIFACT', output)
    print('BYTES', output.stat().st_size)
    print('SHA256', sha(output.read_bytes()))


if __name__ == '__main__':
    build()
