"""Package a compact report-only review; preserve all successful power/tool outputs."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
source_run="$HOME/soc/tpusoc_system_power_20261107_L4HT7n"
[[ -s "$source_run/SystemPowerSummary.json" ]] || { echo 'ERROR: completed system power report required'; exit 2; }
work=$(mktemp -d "$HOME/soc/tpusoc_system_power_review_20261107_XXXXXX")
tools="$work/tools"; mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: SYSTEM_POWER_REVIEW_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: existing power/coverage/mapping documents only; no DC or simulation; original estimates retained'
''']
hashes=[]
for index,name in enumerate(('Prepare.py','PowerCoverage.py','SystemPowerReview.py','StageWatch.py')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n'); marker=f'TPUSOC_POWER_REVIEW_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_POWER_REVIEW_HASHES\'\n'+''.join(hashes)+'TPUSOC_POWER_REVIEW_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
if ! python3 -B -u "$tools/StageWatch.py" --label review_existing_power_reports --limit 180 --log "$work/review.log" --cwd "$work" -- \
    python3 -B -u "$tools/SystemPowerReview.py" "$work" --source "$source_run"; then
    tail -n 22 "$work/review.log"; exit 1
fi
cat "$work/review.log"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode(); out=ROOT/'workspace/Server/tpusoc_system_power_review_20261107_v1.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
