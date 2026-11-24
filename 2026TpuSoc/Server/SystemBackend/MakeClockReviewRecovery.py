"""Build a summary-only recovery of existing clock-port/area reports."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
work="$HOME/soc/tpusoc_clock_port_review_20261106_TiLrj3"
[[ -s "$work/Inputs.json" && -s "$work/area_breakdown.tsv" ]] || { echo "ERROR: Completed report run not found: $work"; exit 2; }
tools=$(mktemp -d "$work/summary_recovery_v1_XXXXXX")
echo "WORK_DIR: $work"
echo 'MODE: summary/SDC-format verification/archive only; no DC, synthesis or simulation'
echo 'EXISTING_AREA_BREAKDOWN: raw completed report; final checks follow'
cat "$work/area_breakdown.tsv"
''']
hashes=[]
for index,name in enumerate(('Prepare.py','ClockPortReview.py','RecoverClockReview.py','StageWatch.py')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    marker=f'TPUSOC_CLOCK_SUMMARY_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_CLOCK_SUMMARY_HASHES\'\n'+''.join(hashes)+'TPUSOC_CLOCK_SUMMARY_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
if ! python3 -B -u "$tools/StageWatch.py" --label recover_summary --limit 180 --log "$tools.log" --cwd "$work" -- python3 -B -u "$tools/RecoverClockReview.py" "$work"; then
    tail -n 24 "$tools.log"; exit 1
fi
cat "$tools.log"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode()
out=ROOT/'workspace/Server/tpusoc_clock_summary_recovery_20261106_v1.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
