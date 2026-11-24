"""Build a bounded continuation retaining the completed FF1 simulation/SAIF."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
old="$HOME/soc/tpusoc_system_tasks_20261106_ZBysEH"
[[ -x "$old/simv" && -s "$old/ff1/task.saif" ]] || { echo "ERROR: completed FF1 run/binary missing: $old"; exit 2; }
vcs_support=${VCS_BIN:-/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs}
export PATH="$(dirname "$vcs_support"):$PATH"
work=$(mktemp -d "$old/resume_20261107_XXXXXX")
tools="$work/tools"; mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify_and_validate_existing_ff1
trap 'rc=$?; if ((rc)); then echo "RESULT: SYSTEM_TASK_RESUME_FAILED stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo "EXISTING_TASK_RUN: $old"
echo 'MODE: preserve successful FF1 and compiled binary; parse native SAIF numbers/units; run only missing encoder'
echo 'LIMIT: input/FF1 validation 5min; encoder simulation 30min; final validation 5min; no synthesis, recompile or DC power'
''']
hashes=[]
for index,name in enumerate(('Prepare.py','SystemTasks.py','ResumeSystemTasks.py','StageWatch.py')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    marker=f'TPUSOC_SYSTEM_RESUME_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_SYSTEM_RESUME_HASHES\'\n'+''.join(hashes)+'TPUSOC_SYSTEM_RESUME_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
run_stage() {
    local label=$1 limit=$2 log=$3
    shift 3
    python3 -B -u "$tools/StageWatch.py" --label "$label" --limit "$limit" --log "$log" --cwd "$old" -- "$@"
}
if ! run_stage verify_existing_ff1 300 "$work/ff1_validate.log" python3 -B -u "$tools/ResumeSystemTasks.py" prepare "$work" --task-run "$old"; then
    tail -n 24 "$work/ff1_validate.log"; exit 1
fi
cat "$work/ff1_validate.log"
bundle=$(cat "$old/Bundle.txt"); firmware=$(cat "$old/Firmware.txt")
stage=simulate_encoder
if ! run_stage simulate_encoder 1800 "$old/encoder/run.log" "$old/simv" +INIT_ALL=1 +INIT_PATTERN=2 \
    +RESET_X_LIST="$old/encoder/reset_x.txt" +TASK_SAIF="$old/encoder/task.saif" \
    +FIRMWARE="$firmware" +VECTORS="$bundle/Vectors" +KIND=0 +LAYERS=1; then
    tail -n 28 "$old/encoder/run.log"; exit 1
fi
grep -E '^(PASS PHYSICAL_TCM_INIT:|PASS SHARED:|PASS SHARED_TCM_GUARD:|INIT_FINAL:|TASK_ACTIVITY_END:)' "$old/encoder/run.log"
stage=validate_and_summarize
if ! run_stage validate_and_summarize 300 "$work/final.log" python3 -B -u "$tools/ResumeSystemTasks.py" finish "$work"; then
    tail -n 24 "$work/final.log"; exit 1
fi
cat "$work/final.log"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode()
out=ROOT/'workspace/Server/tpusoc_system_tasks_resume_20261107_v1.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
