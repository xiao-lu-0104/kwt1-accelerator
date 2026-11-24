"""Create an offline pluma-transfer launcher for the exact new frontend."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import textwrap

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[2]
FRONT=WORKSPACE/'2026TpuSoc_frontend_20261113_6bb1bea'
REV='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6'
CPU='9f3e34f337f5d0a1236a285871ffa2032491617a'
TOOLS=HERE.parent/'Submission20261113'


def sha(b):return hashlib.sha256(b).hexdigest()


def main():
    if subprocess.check_output(['git','-C',str(FRONT),'rev-parse','HEAD']).decode().strip()!=REV:raise ValueError('Wrong frontend')
    files={}
    def extract(repo,rev,paths,prefix):
        raw=subprocess.check_output(['git','-C',str(repo),'archive',rev]+paths)
        with tarfile.open(fileobj=io.BytesIO(raw)) as t:
            for m in t:
                if m.isfile():files[prefix+m.name]=t.extractfile(m).read()
    extract(FRONT,REV,['Rtl','Backend','Sim','Sw','Model','Server/SingleClock/LocalTest.sh','Server/SingleClock/MakeLocalTest.py','Makefile','README.md','.gitmodules'],'source/')
    for n in ['SubmissionAccelerator.sv','Constraints.tcl']:
        files['integration/'+n]=(HERE/n).read_bytes().replace(b'\r\n',b'\n')
    files['integration/SpFoundry.sv']=(HERE.parent/'Backend/SpFoundry.sv').read_bytes().replace(b'\r\n',b'\n')
    names='TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer TpuMatmul TpuGelu TpuVector TpuDma TpuLocalCopy TpuFf1Stream TpuIcb TpuTop TpuNice'.split()
    sources=['source/Rtl/'+n+'.sv' for n in names]+['integration/SpFoundry.sv','integration/SubmissionAccelerator.sv']
    files['AcceleratorSources.json']=(json.dumps(sources,indent=2)+'\n').encode()
    files['RunAccelerator.py']=(HERE/'RunAccelerator.py').read_bytes().replace(b'\r\n',b'\n')
    for n in ['Dc.tcl','AsicCommon.tcl']:
        files['tools/'+n]=(TOOLS/n).read_bytes().replace(b'\r\n',b'\n')
    files['tools/NativeHelpers.py']=(HERE/'NativeHelpers.py').read_bytes().replace(b'\r\n',b'\n')
    files['SourceManifest.json']=(json.dumps({'source_commit':REV,'cpu_gitlink':CPU,
        'scope':'16-MAC accelerator with ICB32 and 56 private SRAM; excludes new CPU/DMA SystemBus arbiter and original CPU/shared SRAM; diagnostic accelerator boundary, not complete system area',
        'formal_performance':'new cold-task 12-audio evaluation still required; do not reuse prefetch-batch/legacy throughput',
        'integration_files':['integration/SubmissionAccelerator.sv','integration/SpFoundry.sv','integration/Constraints.tcl'],
        'files_sha256':{n:sha(b) for n,b in sorted(files.items())}},indent=2)+'\n').encode()
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as t:
        for n,b in sorted(files.items()):
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o644;m.mtime=1794528000;t.addfile(m,io.BytesIO(b))
    data=buf.getvalue()
    release=WORKSPACE/'release/newdc_6bb1bea';release.mkdir(exist_ok=True)
    (release/'payload.tar.gz').write_bytes(data)
    script='''#!/usr/bin/env bash
set -euo pipefail
umask 077
root="/tmp/final_dc_6bb1bea_$(id -u)"
if [[ -f "$root/SourceManifest.json" ]]; then
    echo "SOURCE_ALREADY_IMPORTED=$root"
else
    mkdir -p "$root"
    base64 -d > "$root/payload.tar.gz" <<'NEW_6BB1BEA_SOURCE'
'''+textwrap.fill(base64.b64encode(data).decode(),76)+'''
NEW_6BB1BEA_SOURCE
    tar -xzf "$root/payload.tar.gz" -C "$root"
fi
cache="/tmp/final_7cf5155_pdk_$(id -u)"
if [[ ! -f "$cache/CleanupComplete.txt" ]]; then
    echo 'STOP: previous PDK cache unavailable; keep existing files and inspect /tmp/final_7cf5155_pdk_UID'
    exit 2
fi
exec > >(tee -a "$root/runner.log") 2>&1
echo "WORK_DIR=$root"
python3 -u "$root/RunAccelerator.py" "$root" --cache "$cache"
'''
    (release/'RunNewDc_6bb1bea.sh').write_text(script,encoding='utf-8',newline='\n')
    save={'source_commit':REV,'files':len(files),'payload_bytes':len(data),'script_bytes':len(script),'payload_sha256':sha(data)}
    (release/'Build.json').write_text(json.dumps(save,indent=2)+'\n')
    print(json.dumps(save,indent=2))


if __name__=='__main__':main()
