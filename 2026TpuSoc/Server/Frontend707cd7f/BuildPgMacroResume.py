"""Generate immutable macro-only recovery from the native-saved rails library."""
import base64
import io
import json
import tarfile
from BuildPr import HERE,ROOT,sha
from BuildPgResume import once


def build_files():
    frozen=ROOT/'Doc/DCScripts_20261110_707cd7f/pg_resume_v1'
    files={}
    for line in (frozen/'PACKAGE.sha256').read_text().splitlines():
        digest,name=line.split('  ',1);data=(frozen/name).read_bytes()
        if sha(data)!=digest:raise ValueError('Frozen rails source changed: '+name)
        files[name]=data
    stage=files['tools/PgStage.tcl'].decode()
    start=stage.index('            PgConnect\n            PrStep ring_pattern')
    end=stage.index('            # The installed manual permits omitted contact_code;',start)
    stage=stage[:start]+'''            # Continue only the saved rails library; existing ring/mesh/rails stay intact.
            PgConnect
'''+stage[end:]
    stage=once(stage,'-via_rule {{{layers: M4} {layers: M5} {via_master: PIN707_1X1}}}',
        '-via_rule {{intersection: adjacent} {via_master: PIN707_1X1}}')
    # No unused baseline audit branch in the executable recovery Tcl.
    start=stage.index('        audit_baseline {');end=stage.index('        pg_core {',start)
    stage=stage[:start]+stage[end:]
    files['tools/PgStage.tcl']=stage.encode()
    flow=files['tools/PgFlow.py'].decode()
    flow=once(flow,'from PgResumeInputs import select_recovered','from PgRailsInputs import select_rails')
    flow=once(flow,"recovery=select_recovered(Path.home()/'soc',source,cfg)","recovery=select_rails(Path.home()/'soc',source,cfg)")
    flow=flow.replace('RECOVERED_LEGALIZED_DIAGNOSTIC:','RECOVERED_RAILS_CHECKPOINT:')
    flow=once(flow,"glob('tpusoc_pg_resume_20261110_707cd7f_*/PgInputs.json')","glob('tpusoc_pg_macro_resume_20261110_707cd7f_*/PgInputs.json')")
    flow=once(flow,".get('recovered_diagnostic')==recovery['diagnostic']",".get('recovered_rails_run')==recovery['rails_run']")
    flow=once(flow,"'resume_scope':'audit original library, then recovered PG; no legalize rerun'",
        "'recovered_rails_run':recovery['rails_run'],'resume_scope':'saved rails to macro connection and independent checks only'")
    flow=once(flow,"audit=out/'audit_baseline'","audit=Path(recovery['audit'])")
    flow=once(flow,"for kind,tag in [('audit_baseline','baseline_audited'),('pg_core','pg_complete')]:",
        "for kind,tag in [('pg_core','pg_complete')]:")
    flow=flow.replace('Saved diagnostic library changed','Saved rails library changed')
    files['tools/PgFlow.py']=flow.encode()
    files['tools/PgRailsInputs.py']=(HERE/'PgRailsInputs.py').read_bytes().replace(b'\r\n',b'\n')
    cfg=json.loads(files['Config.json'].decode());cfg.update(rails_manifest_sha256=sha((frozen/'PACKAGE.sha256').read_bytes()),
        scope='copy native rails checkpoint; macro pattern uses installed intersection grammar; independent PG connectivity and DRC')
    files['Config.json']=(json.dumps(cfg,indent=2)+'\n').encode()
    return files


def main():
    files=build_files();files['PACKAGE.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as z:
        for n,b in sorted(files.items()):
            t=tarfile.TarInfo(n);t.size=len(b);t.mode=0o644;t.mtime=1704067200;z.addfile(t,io.BytesIO(b))
    data=buf.getvalue();name='tpusoc_pg_macro_resume_20261110_707cd7f_v1.sh'
    entry='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_pg_macro_resume_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'MACRO_RESUME_707'
'''+base64.encodebytes(data).decode()+'''MACRO_RESUME_707
echo "'''+sha(data)+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "PG_MACRO_RESUME_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/PgFlow.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    p=ROOT/'workspace/Server'/name
    with p.open('xb') as f:f.write(entry.encode())
    digest=sha(p.read_bytes())
    oldname='tpusoc_pg_resume_20261110_707cd7f_v1.sh';oldhash='77c139483361d2f73633a50641615b17f64e21db8791411600d63f825da638c5'
    command=(HERE/'NormalizePgResumeCommand.txt').read_text().replace(oldname,name).replace(oldhash,digest).replace('tpusoc_pg_resume_20261110_707cd7f_verified.sh','tpusoc_pg_macro_resume_20261110_707cd7f_verified.sh')
    helper=(HERE/'CopyPgResumeToClipboard.ps1').read_text().replace(oldname,name).replace(oldhash,digest).replace('NormalizePgResumeCommand.txt','NormalizePgMacroResumeCommand.txt')
    (HERE/'NormalizePgMacroResumeCommand.txt').write_text(command)
    (HERE/'CopyPgMacroResumeToClipboard.ps1').write_text(helper)
    target=ROOT/'Doc/DCScripts_20261110_707cd7f/pg_macro_resume_v1';target.mkdir()
    for n,b in files.items():
        q=target/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
    for q in (HERE/'BuildPgMacroResume.py',HERE/'PgRailsInputs.py',HERE/'NormalizePgMacroResumeCommand.txt',HERE/'CopyPgMacroResumeToClipboard.ps1',p):
        (target/q.name).write_bytes(q.read_bytes())
    print(name,len(entry.encode()),digest)


if __name__=='__main__':main()
