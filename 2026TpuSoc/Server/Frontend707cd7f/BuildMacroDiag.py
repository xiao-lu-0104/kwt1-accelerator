import base64
import io
import json
import tarfile
from BuildPr import HERE,ROOT,sha


def build_files():
    return {'tools/MacroDiag.py':(HERE/'MacroDiag.py').read_bytes().replace(b'\r\n',b'\n'),
            'Config.json':(json.dumps({'pg_manifest_sha256':sha((ROOT/'Doc/DCScripts_20261110_707cd7f/pg_v1/PACKAGE.sha256').read_bytes()),
                'scope':'diagnostic copy only; capture before/fixed/keepout/legalized; do not build PG or accept modified macro positions'},indent=2)+'\n').encode()}


def main():
    files=build_files();files['PACKAGE.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode();buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as z:
        for n,b in sorted(files.items()):
            t=tarfile.TarInfo(n);t.size=len(b);t.mode=0o644;t.mtime=1704067200;z.addfile(t,io.BytesIO(b))
    data=buf.getvalue()
    entry='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_macro_diag_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'MACRO_DIAG_707CD7F'
'''+base64.encodebytes(data).decode()+'''MACRO_DIAG_707CD7F
echo "'''+sha(data)+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "MACRO_DIAG_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/MacroDiag.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    name='tpusoc_macro_diag_20261110_707cd7f_v1.sh';p=ROOT/'workspace/Server'/name
    with p.open('xb') as f:f.write(entry.encode())
    digest=sha(p.read_bytes());template=(HERE/'NormalizePgCommand.txt').read_text()
    template=template.replace('tpusoc_pg_20261110_707cd7f_v1.sh',name).replace('tpusoc_pg_20261110_707cd7f_verified.sh','tpusoc_macro_diag_20261110_707cd7f_verified.sh')
    template=template.replace('d15bbe174d9563451a68b3d16a4ea668de29452e8cb4b353935fb15cb142dceb',digest)
    (HERE/'NormalizeMacroDiagCommand.txt').write_text(template)
    helper=(HERE/'CopyPgToClipboard.ps1').read_text().replace('tpusoc_pg_20261110_707cd7f_v1.sh',name)
    helper=helper.replace('d15bbe174d9563451a68b3d16a4ea668de29452e8cb4b353935fb15cb142dceb',digest).replace('NormalizePgCommand.txt','NormalizeMacroDiagCommand.txt')
    (HERE/'CopyMacroDiagToClipboard.ps1').write_text(helper)
    print(name,len(entry.encode()),digest)


if __name__=='__main__':main()
