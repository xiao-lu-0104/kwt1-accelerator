"""Package the tested startup firmware and two guarded system task reruns."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
old="$HOME/soc/tpusoc_system_tasks_20261106_ZBysEH"
[[ -x "$old/simv" && -s "$old/ff1/Activity.json" && -s "$old/encoder/run.log" ]] || { echo 'ERROR: original task evidence/simulator required'; exit 2; }
work=$(mktemp -d "$HOME/soc/tpusoc_boot_gpr_fix_20261107_XXXXXX")
tools="$work/tools"; mkdir -p "$tools" "$work/ff1" "$work/encoder" "$work/firmware/Sw" "$work/firmware/BuildEvidence"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: BOOT_GPR_FIX_FAILED stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: boot firmware initializes CPU GPRs by normal instructions; original compiled simulator/RTL/golden/strict X guards preserved'
echo 'LIMIT: verification 5min; encoder 45min; FF1 20min; each validation 5min; limits are caps, not runtime promises'
echo 'SCOPE: both tasks rerun with new firmware; original successful FF1 preserved separately; no synthesis or DC power in this stage'
''']
files={f'tools/{name}':HERE/name for name in ('Prepare.py','StageWatch.py','BootFirmware.py','SystemTasks.py','BootFixTasks.py')}
fixed=ROOT/'workspace/Checks/BootGprFix_20261107_v1/fixed'
for path in sorted(fixed.rglob('*')):
    if path.is_file(): files['firmware/'+path.relative_to(fixed).as_posix()]=path
hashes=[]
for index,(name,path) in enumerate(files.items()):
    data=path.read_bytes()
    payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
    digest=hashlib.sha256(data).hexdigest()
    parts.append('python3 - "$work/'+name+'" <<\'TPUSOC_BOOT_FILE_'+str(index)+"'\n"+
        'import base64,gzip,hashlib,sys\nfrom pathlib import Path\n'+
        'data=gzip.decompress(base64.b64decode("'+payload+'"))\n'+
        'assert hashlib.sha256(data).hexdigest()=="'+digest+'"\nPath(sys.argv[1]).write_bytes(data)\n'+
        'TPUSOC_BOOT_FILE_'+str(index)+'\n')
    hashes.append(digest+'  '+name+'\n')
parts.append('cat > "$work/PACKAGE.sha256" <<\'TPUSOC_BOOT_HASHES\'\n'+''.join(hashes)+'TPUSOC_BOOT_HASHES\n')
parts.append('''(cd "$work"; sha256sum --quiet -c PACKAGE.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
run_stage() {
    local label=$1 limit=$2 log=$3
    shift 3
    python3 -B -u "$tools/StageWatch.py" --label "$label" --limit "$limit" --log "$log" --cwd "$old" -- "$@"
}
if ! run_stage prepare 300 "$work/prepare.log" python3 -B -u "$tools/BootFixTasks.py" prepare "$work" --task-run "$old"; then
    tail -n 22 "$work/prepare.log"; exit 1
fi
cat "$work/prepare.log"
bundle=$(cat "$work/Bundle.txt"); firmware=$(cat "$work/Firmware.txt")
for task in encoder ff1; do
    kind=0; limit=2700; vectors="$bundle/Vectors"
    if [[ "$task" == ff1 ]]; then kind=1; limit=1200; vectors="$vectors/Ff1_normal"; fi
    stage="simulate_$task"
    if ! run_stage "$stage" "$limit" "$work/$task/run.log" "$old/simv" +INIT_ALL=1 +INIT_PATTERN=2 \
        +RESET_X_LIST="$work/$task/reset_x.txt" +TASK_SAIF="$work/$task/task.saif" \
        +FIRMWARE="$firmware" +VECTORS="$vectors" +KIND="$kind" +LAYERS=1; then
        tail -n 28 "$work/$task/run.log"; exit 1
    fi
    grep -E '^(PASS PHYSICAL_TCM_INIT:|PASS SHARED:|PASS SHARED_TCM_GUARD:|INIT_FINAL:|TASK_ACTIVITY_END:)' "$work/$task/run.log" || true
    stage="validate_$task"
    if ! run_stage "$stage" 300 "$work/$task/validate.log" python3 -B -u "$tools/BootFixTasks.py" validate "$work" --task "$task"; then
        tail -n 28 "$work/$task/run.log"; tail -n 20 "$work/$task/validate.log"; exit 1
    fi
    cat "$work/$task/validate.log"
done
stage=summarize
if ! run_stage summarize 300 "$work/summary.log" python3 -B -u "$tools/BootFixTasks.py" finish "$work"; then
    tail -n 20 "$work/summary.log"; exit 1
fi
cat "$work/summary.log"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode()
out=ROOT/'workspace/Server/tpusoc_boot_gpr_fix_20261107_v1.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
