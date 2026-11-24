"""Package fresh 1109 system placement code without vendor material."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    files={'tools/'+n:(HERE/n).read_bytes() for n in ('Run.py','Place.tcl')}
    for n in ('PrLibrary.tcl','PrCommon.tcl','Preflight.py'):
        files['tools/'+n]=(ROOT/'Server/FinalBackend'/n).read_bytes()
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
work=$(mktemp -d "$HOME/soc/tpusoc_new_system_pr_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'NEW_SYSTEM_PR_PAYLOAD'
'''+base64.encodebytes(data).decode()+'''NEW_SYSTEM_PR_PAYLOAD
echo "'''+hashlib.sha256(data).hexdigest()+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "NEW_SYSTEM_PR_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
echo 'DESIGN: only current 1109 e203_cpu_top netlist/SDC; 56 private + 64 shared SRAM'
echo 'OUTPUT: initial geometric placement/nlib/DEF; PG straps/RC/CTS/route remain subsequent work'
python3 -u "$work/tools/Run.py" "$work"
'''
    path=ROOT/'workspace/Server/tpusoc_new_system_pr_20261109_v1.sh'
    if path.exists():raise ValueError('Refusing to replace versioned artifact')
    path.write_bytes(shell.encode())
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':main()
