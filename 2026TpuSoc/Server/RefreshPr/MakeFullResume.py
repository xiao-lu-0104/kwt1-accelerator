"""Freeze a new recovery package without altering the original frozen full PR."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def patched_stage():
    text=(HERE/'FullStage.tcl').read_text()
    text=text.replace('-check_std_cell_pins true','-check_std_cell_pins all')
    text=text.replace('        pg_connectivity.rpt {check_pg_connectivity -check_macro_pins all -check_std_cell_pins all}\n','')
    text=text.replace('        pg_drc.rpt {check_pg_drc}\n','')
    old='    PrStep save_stage_block [list save_block]\n    PrStep save_stage_lib [list save_lib]\n    PrStep stage_def [list write_def checkpoint.def]\n'
    if text.count(old)!=1: raise ValueError('Original save protocol changed')
    text=text.replace(old,'')
    marker='    foreach {File Command} {\n        qor.rpt'
    if text.count(marker)!=1: raise ValueError('Original report protocol changed')
    text=text.replace(marker,old+'    puts "FULL_PR_CORE_SAVED: $Phase";flush stdout\n'+marker)
    if '-check_std_cell_pins true' in text or 'Check pg_drc.rpt' in text:
        raise ValueError('Invalid recovery stage')
    return text.encode()


def main():
    files={'tools/'+n:(HERE/n).read_bytes() for n in ('ResumeFull.py','FullRun.py','PgCheck.tcl')}
    files['tools/ResumeStage.tcl']=patched_stage()
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
work=$(mktemp -d "$HOME/soc/tpusoc_full_pr_recovery_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'RECOVERY_PAYLOAD'
'''+base64.encodebytes(data).decode()+'''RECOVERY_PAYLOAD
echo "'''+hashlib.sha256(data).hexdigest()+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "PR_FULL_RECOVERY_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u "$work/tools/ResumeFull.py" "$work"
'''
    path=ROOT/'workspace/Server/tpusoc_full_pr_recovery_20261109_v1.sh'
    if path.exists(): raise ValueError('Frozen recovery entry already exists')
    path.write_bytes(shell.encode())
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':main()
