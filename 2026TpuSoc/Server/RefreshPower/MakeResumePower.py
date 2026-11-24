"""Freeze small power-only recovery; never changes the v1 simulation package."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    files={'ResumePower.py':(HERE/'ResumePower.py').read_bytes()}
    for name in ('Power.py','Power.tcl'):files['replacement/'+name]=(HERE/name).read_bytes()
    files['PACKAGE.sha256']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mtime=1704067200
            tar.addfile(info,io.BytesIO(data))
    data=buffer.getvalue()
    shell='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_power_resume_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'CURRENT_POWER_RESUME_PAYLOAD'
'''+base64.encodebytes(data).decode()+'''CURRENT_POWER_RESUME_PAYLOAD
echo "'''+hashlib.sha256(data).hexdigest()+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "POWER_RESUME_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u "$work/ResumePower.py" "$work"
'''
    path=ROOT/'workspace/Server/tpusoc_power_resume_20261109_v1.sh'
    if path.exists():raise ValueError('Refusing to replace versioned recovery')
    path.write_bytes(shell.encode())
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':main()
