"""Immutable 1111 continuation: qualify 1110 v6, bounded PG repair, then CTS/route."""
import base64
import io
import json
import tarfile
from BuildPr import HERE,ROOT,sha


def build_files():
    frozen=ROOT/'Doc/DCScripts_20261110_707cd7f/pg_macro_resume_v1'
    files={}
    for line in (frozen/'PACKAGE.sha256').read_text().splitlines():
        digest,name=line.split('  ',1);data=(frozen/name).read_bytes()
        if sha(data)!=digest:raise ValueError('Frozen predecessor differs: '+name)
        files[name]=data
    for name in ('ContinuePr.py','ContinuePr.tcl','PgPhysical.tcl'):
        files['tools/'+name]=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    # Helpers only: no 1109 design main/selection code is deployed or executed.
    rc=(ROOT/'Server/RefreshPr/FullRun.py').read_text().split('\ndef main(out):',1)[0]
    rc=rc.replace("'model':'TYP1109'","'model':'TYP707CONT'")
    files['tools/RcHelpers.py']=rc.encode()
    cfg=json.loads(files['Config.json'].decode())
    cfg['scope']='verified 707cd7f v6 checkpoint; <=2 additive PG trials; authorized CTS and signal routing with unresolved PG retained'
    cfg['execution_date']='2026-11-11'
    cfg['not_signoff']=True
    files['Config.json']=(json.dumps(cfg,indent=2)+'\n').encode()
    return files


def main():
    files=build_files();files['PACKAGE.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=1704067200
            tar.addfile(info,io.BytesIO(data))
    data=buf.getvalue()
    name='tpusoc_continue_pr_20261111_707cd7f_v1.sh'
    shell='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_continue_pr_20261111_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'CONTINUE707'
'''+base64.encodebytes(data).decode()+'''CONTINUE707
echo "'''+sha(data)+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "CONTINUE_PR_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/ContinuePr.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    path=ROOT/'workspace/Server'/name
    with path.open('xb') as f:f.write(shell.encode())
    digest=sha(path.read_bytes())
    oldname='tpusoc_pg_macro_resume_20261110_707cd7f_v1.sh'
    oldhash='be9d5c1b22d43362713282b7cdf9b93279c20253422bb1f1568178b53acc2575'
    command=(HERE/'NormalizePgMacroResumeCommand.txt').read_text().replace(oldname,name).replace(oldhash,digest)
    command=command.replace('tpusoc_pg_macro_resume_20261110_707cd7f_verified.sh','tpusoc_continue_pr_20261111_707cd7f_verified.sh')
    (HERE/'NormalizeContinuePrCommand.txt').write_text(command)
    helper=(HERE/'CopyPgMacroResumeToClipboard.ps1').read_text().replace(oldname,name).replace(oldhash,digest)
    helper=helper.replace('NormalizePgMacroResumeCommand.txt','NormalizeContinuePrCommand.txt')
    (HERE/'CopyContinuePrToClipboard.ps1').write_text(helper)
    target=ROOT/'Doc/DCScripts_20261110_707cd7f/continue_pr_20261111_v1'
    target.mkdir()
    for n,b in files.items():
        p=target/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    for p in (HERE/'BuildContinuePr.py',HERE/'NormalizeContinuePrCommand.txt',HERE/'CopyContinuePrToClipboard.ps1',path):
        (target/p.name).write_bytes(p.read_bytes())
    print(name,len(shell.encode()),digest)


if __name__=='__main__':main()
