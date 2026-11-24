"""Package a bounded offline collection of completed backend evidence."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
source_run=$(python3 - "$HOME/soc" <<'TPUSOC_SELECT_COMPLETED_POWER'
import json,sys
from pathlib import Path
choices=sorted(Path(sys.argv[1]).glob('tpusoc_system_power_auto_active_20261107_*'),key=lambda p:p.stat().st_mtime,reverse=True)
for path in choices:
    file=path/'SystemPowerSummary.json'
    if not file.exists(): continue
    record=json.loads((path/'Inputs.json').read_text())
    if record.get('require_active_mapping'):
        print(path); break
else: raise SystemExit('ERROR: a completed active-mapping power report is required')
TPUSOC_SELECT_COMPLETED_POWER
)
work=$(mktemp -d "$HOME/soc/tpusoc_backend_materials_20261107_XXXXXX")
tools="$work/tools"; mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: BACKEND_MATERIALS_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo "POWER_REPORT_SOURCE: $source_run"
echo 'MODE: verify and package existing sources/netlist/SDC/area/timing/task SAIF/power; no DC, synthesis or simulation'
echo 'LIMIT: verification/copy/archive 10min; explicit default/X activity and platform-boundary limitations retained'
''']
files={name:HERE/name for name in ('Prepare.py','BackendMaterials.py','StageWatch.py')}
for name in ('功耗原始报告_20261107.md','面积分配_20261106.md'): files[name]=ROOT/'Doc'/name
hashes=[]
for index,(name,path) in enumerate(files.items()):
    data=path.read_bytes().replace(b'\r\n',b'\n'); marker=f'TPUSOC_BACKEND_MATERIAL_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_BACKEND_MATERIAL_HASHES\'\n'+''.join(hashes)+'TPUSOC_BACKEND_MATERIAL_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
if ! python3 -B -u "$tools/StageWatch.py" --label collect_backend_materials --limit 600 --log "$work/collect.log" --cwd "$work" -- \
    python3 -B -u "$tools/BackendMaterials.py" "$work" --source "$source_run"; then
    tail -n 24 "$work/collect.log"; exit 1
fi
cat "$work/collect.log"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode(); out=ROOT/'workspace/Server/tpusoc_backend_materials_20261107_v2.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
