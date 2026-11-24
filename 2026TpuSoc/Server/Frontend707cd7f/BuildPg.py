"""Freeze an actual new-707cd7f PG flow, not a historical frozen runner."""
import base64
import io
import json
import tarfile
from BuildPr import build_files as helper_files, HERE, ROOT, sha


def build_files():
    files={'tools/PrHelpers.py':helper_files()['tools/PrHelpers.py']}
    for p in [HERE/n for n in ('PgFlow.py','PgStage.tcl','PgCheck.tcl','SystemFlow.py')]+[
            ROOT/'Server/FinalBackend/PrCommon.tcl',ROOT/'Server/FinalBackend/Preflight.py',ROOT/'Server/SystemBackend/StageWatch.py']:
        files['tools/'+p.name]=p.read_bytes().replace(b'\r\n',b'\n')
    frozen=ROOT/'Doc/DCScripts_20261110_707cd7f/initial_pr_v2'
    regular=(frozen/'tools/RegularIo.tcl').read_text(encoding='utf-8')
    if regular.count('foreach {N O} {')!=1:raise ValueError('Expected one helper/runner boundary')
    # Definitions only. Never source the IO placement runner during PG.
    files['tools/IoGeometry.tcl']=regular.split('foreach {N O} {',1)[0].encode()
    files['tools/PinPlan.py']=(frozen/'tools/PinPlan.py').read_bytes()
    files['Config.json']=(json.dumps({'source_commit':'707cd7f4a0a4d416d11bac71112980079e0a9d34',
        'initial_package_sha256':sha((frozen/'PACKAGE.sha256').read_bytes()),
        'scope':'legalize and actual42um PG on copied new grouped-IO checkpoint; independent checks; no signal routing',
        'limits_seconds':{'legalize':3600,'pg_core':3600,'connectivity':1800,'drc':3600}},indent=2)+'\n').encode()
    return files


def main():
    files=build_files();files['PACKAGE.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as z:
        for n,b in sorted(files.items()):
            t=tarfile.TarInfo(n);t.size=len(b);t.mode=0o644;t.mtime=1704067200;z.addfile(t,io.BytesIO(b))
    data=buf.getvalue()
    entry='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_pg_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'ACTUAL_PG_707CD7F'
'''+base64.encodebytes(data).decode()+'''ACTUAL_PG_707CD7F
echo "'''+sha(data)+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "PG_FLOW_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/PgFlow.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    name='tpusoc_pg_20261110_707cd7f_v1.sh';p=ROOT/'workspace/Server'/name
    with p.open('xb') as f:f.write(entry.encode())
    digest=sha(p.read_bytes())
    command=(HERE/'NormalizeLayoutApiCommand.txt').read_text().replace('tpusoc_layout_api_20261110_707cd7f_v1.sh',name)
    command=command.replace('tpusoc_layout_api_20261110_707cd7f_verified.sh','tpusoc_pg_20261110_707cd7f_verified.sh')
    command=command.replace('ae13d79a5d003010ab8b40c7ef312be0fff95ad877c170ce7d869c389e666d5e',digest)
    (HERE/'NormalizePgCommand.txt').write_text(command)
    helper=(HERE/'CopyLayoutApiToClipboard.ps1').read_text().replace('tpusoc_layout_api_20261110_707cd7f_v1.sh',name)
    helper=helper.replace('ae13d79a5d003010ab8b40c7ef312be0fff95ad877c170ce7d869c389e666d5e',digest)
    helper=helper.replace('NormalizeLayoutApiCommand.txt','NormalizePgCommand.txt').replace('Frozen layout API probe','Frozen new PG entry')
    (HERE/'CopyPgToClipboard.ps1').write_text(helper)
    print(name,len(entry.encode()),digest)


if __name__=='__main__':main()
