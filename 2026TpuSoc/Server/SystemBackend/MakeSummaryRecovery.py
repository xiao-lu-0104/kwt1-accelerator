"""Build a summary-only recovery entry; existing EDA outputs and inputs stay intact."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
work="$HOME/soc/tpusoc_system_base_20261106_GamjxW"
[[ -f "$work/SystemBaseInputs.json" ]] || { echo "ERROR: Expected run not found: $work"; exit 2; }
tools=$(mktemp -d "$work/summary_recovery_v1_XXXXXX")
echo "WORK_DIR: $work"
echo 'MODE: verify original frozen prefix and all other inputs; summary/archive only; no synthesis or simulation'
''']
hashes=[]
for index,name in enumerate(('Prepare.py','Summarize.py','RecoverSummary.py')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    marker=f'TPUSOC_RECOVERY_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_RECOVERY_HASHES\'\n'+''.join(hashes)+'TPUSOC_RECOVERY_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools" python3 -B -u "$tools/RecoverSummary.py" "$work" 2>&1 | tee "$tools/recovery.log"
''')
# Keep the runtime recovery.log out of the tool input manifest by placing it outside tools.
parts[-1]=parts[-1].replace('"$tools/recovery.log"','"$tools.log"')
data=''.join(parts).encode()
out=ROOT/'workspace/Server/tpusoc_system_summary_recovery_20261106_v1.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest()
payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
