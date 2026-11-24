"""Package source-only system refresh scripts, preserving existing artifacts."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    original=ROOT/'workspace/Server/tpusoc_refresh_dc_20261109_v1.sh'
    if hashlib.sha256(original.read_bytes()).hexdigest()!='4edc335d7c8166ca8afdccecca91d302630f179d6ce7210f94254f97c9c6330b':
        raise ValueError('Original accelerator entry changed')
    data=base64.b64decode(original.read_text().split("<<'TPUSOC_REFRESH_PAYLOAD'\n",1)[1].split('\nTPUSOC_REFRESH_PAYLOAD',1)[0])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        manifest_sha=hashlib.sha256(archive.extractfile('MANIFEST.sha256').read()).hexdigest()
    paths=[HERE/'System.py',HERE/'System.tcl',HERE/'Review.py',
        ROOT/'Server/SystemBackend/StageWatch.py',ROOT/'Server/SystemBackend/TcmMacro.sv',
        ROOT/'Server/SystemBackend/AreaBreakdown.tcl',ROOT/'Server/Backend/AsicCommon.tcl']
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for path in paths:
            data=path.read_bytes().replace(b'\r\n',b'\n')
            info=tarfile.TarInfo('tools/'+path.name)
            info.size=len(data)
            info.mtime=1704067200
            archive.addfile(info,io.BytesIO(data))
    data=buffer.getvalue()
    entry='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_new_system_dc_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'TPUSOC_NEW_SYSTEM_PAYLOAD'
'''+base64.encodebytes(data).decode()+'''TPUSOC_NEW_SYSTEM_PAYLOAD
echo "'''+hashlib.sha256(data).hexdigest()+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "SYSTEM_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
python3 -u "$work/tools/System.py" --out "$work" --manifest-sha '''+manifest_sha+'''
'''
    output=ROOT/'workspace/Server/tpusoc_new_system_dc_20261109_v1.sh'
    if output.exists():
        raise ValueError('Refusing to replace versioned artifact')
    output.write_bytes(entry.encode())
    print('ARTIFACT',output)
    print('BYTES',output.stat().st_size)
    print('SHA256',hashlib.sha256(output.read_bytes()).hexdigest())


if __name__=='__main__':
    main()
