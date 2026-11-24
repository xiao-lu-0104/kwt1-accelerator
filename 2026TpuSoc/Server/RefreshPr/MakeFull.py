"""Freeze the full checkpointed 1109 implementation entry."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    files={'tools/'+n:(HERE/n).read_bytes() for n in ('FullRun.py','FullStage.tcl')}
    files['tools/PrCommon.tcl']=(ROOT/'Server/FinalBackend/PrCommon.tcl').read_bytes()
    files['tools/StageWatch.py']=(ROOT/'Server/SystemBackend/StageWatch.py').read_bytes()
    files['PACKAGE.sha256']=''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
        for n,b in sorted(files.items()):
            m=tarfile.TarInfo(n);m.size=len(b);m.mtime=1704067200;tar.addfile(m,io.BytesIO(b))
    data=buffer.getvalue()
    shell='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_full_pr_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'FULL_PR_PAYLOAD'
'''+base64.encodebytes(data).decode()+'''FULL_PR_PAYLOAD
echo "'''+hashlib.sha256(data).hexdigest()+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "FULL_PR_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
echo 'SCOPE: current 1109 full CPU system + 120 SRAM; original layout preserved'
echo 'PHASES: RC, PG, place_opt, clock_opt, route_auto, route_opt, export/checks'
echo 'ACCEPTANCE: routed candidate; actual DRC/timing/PG reports retained, no signoff claimed'
python3 -u "$work/tools/FullRun.py" "$work"
'''
    path=ROOT/'workspace/Server/tpusoc_full_pr_20261109_v1.sh'
    if path.exists():raise ValueError('Refusing to replace frozen artifact')
    path.write_bytes(shell.encode())
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':main()
