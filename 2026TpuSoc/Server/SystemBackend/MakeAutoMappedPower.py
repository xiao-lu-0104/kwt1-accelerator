"""Package a fresh automatic-name-match estimate and regional coverage evidence."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
source_run="$HOME/soc/tpusoc_system_power_20261107_L4HT7n"
[[ -s "$source_run/SystemPowerSummary.json" ]] || { echo 'ERROR: original system power reports required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo 'ERROR: dc_shell not found'; exit 2; }
work=$(mktemp -d "$HOME/soc/tpusoc_system_power_auto_active_20261107_XXXXXX")
tools="$work/tools"; mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: AUTO_MATCH_POWER_FAILED stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: saif_map -start BEFORE read_ddc, then read_saif -auto_map_names; native map NOT loaded; no simulation/synthesis or activity override'
echo 'EVIDENCE: preserve original direct estimate and failed native-map-only attempt; compare full hierarchy and optional regional coverage'
echo 'LIMIT: verify originals 5min; auto-match power 8min/task; summary 5min; limits are caps, not runtime promises'
''']
files={name:HERE/name for name in ('Prepare.py','StageWatch.py','SystemTasks.py','ClockPortReview.py','SystemPower.py',
    'PowerCoverage.py','SystemPower.tcl','NativeMappedPower.py','AutoMappedPower.py')}
for name in ('ReviewTaskPower.py','ReadProbe.py'): files[name]=HERE.parent/'SharedAsic'/name
hashes=[]
for index,(name,path) in enumerate(files.items()):
    data=path.read_bytes().replace(b'\r\n',b'\n'); marker=f'TPUSOC_AUTO_POWER_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_AUTO_POWER_HASHES\'\n'+''.join(hashes)+'TPUSOC_AUTO_POWER_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
run_stage() {
    local label=$1 limit=$2 log=$3
    shift 3
    python3 -B -u "$tools/StageWatch.py" --label "$label" --limit "$limit" --log "$log" --cwd "$work" -- "$@"
}
if ! run_stage prepare 300 "$work/prepare.log" python3 -B -u "$tools/AutoMappedPower.py" prepare "$work" --source "$source_run"; then
    tail -n 24 "$work/prepare.log"; exit 1
fi
cat "$work/prepare.log"
mapfile -t power_paths < <(python3 - "$work/Inputs.json" <<'TPUSOC_AUTO_POWER_PATHS'
import json,sys
data=json.load(open(sys.argv[1])); paths=data['paths']
for value in [paths[key] for key in ('ddc','std_db','private_db','shared_db')]+[data['task_run']]:
    assert '\\n' not in value and '\\r' not in value
    print(value)
TPUSOC_AUTO_POWER_PATHS
)
[[ ${#power_paths[@]} == 5 ]] || { echo 'ERROR: incomplete automatic power paths'; exit 2; }
export TPU_SYSTEM_POWER_DDC="${power_paths[0]}" TPU_STDCELL_DB="${power_paths[1]}"
export TPU_SRAM_DB="${power_paths[2]}" TPU_SYSTEM_DB="${power_paths[3]}" TPU_SYSTEM_NAME_MAP=""
task_run="${power_paths[4]}"
export TPU_SYSTEM_POWER_CASE TPU_SYSTEM_POWER_SAIF
for task in ff1 encoder; do
    stage="auto_power_$task"
    TPU_SYSTEM_POWER_CASE="$work/$task"; TPU_SYSTEM_POWER_SAIF="$task_run/$task/task.saif"
    if ! run_stage "$stage" 480 "$work/$task/dc.log" "$dc_bin" -f "$tools/SystemPower.tcl"; then
        tail -n 28 "$work/$task/dc.log"; exit 1
    fi
    if grep -Eq '^(Error:|SYSTEM_POWER_REPORT_ERROR:)' "$work/$task/dc.log"; then
        tail -n 28 "$work/$task/dc.log"; exit 1
    fi
    grep -E '^(SAIF_MAPPING_ACTIVE_BEFORE_DDC:|SYSTEM_POWER_REPORT_COMPLETE:|OPTIONAL_SYSTEM_POWER_REPORT_UNAVAILABLE:)' "$work/$task/dc.log" || true
done
stage=summarize
if ! run_stage summarize 300 "$work/summary.log" python3 -B -u "$tools/AutoMappedPower.py" finish "$work"; then
    tail -n 24 "$work/summary.log"; exit 1
fi
cat "$work/summary.log"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode(); out=ROOT/'workspace/Server/tpusoc_system_power_auto_20261107_v2.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
