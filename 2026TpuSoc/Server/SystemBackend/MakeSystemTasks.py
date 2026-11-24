"""Package the next physical-TCM full CPU functional/task-SAIF stage."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
review="$HOME/soc/tpusoc_clock_port_review_20261106_TiLrj3"
[[ -s "$review/ClockPortSummary.json" ]] || { echo 'ERROR: recovered clock/area report required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS not found'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_system_tasks_20261106_XXXXXX")
tools="$work/tools"; mkdir -p "$tools" "$work/ff1" "$work/encoder"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: SYSTEM_TASK_STAGE_FAILED stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'SCOPE: original CPU RTL/controllers + frozen mapped accelerator + physical SRAM functional models; no full-system gate/SDF claim'
echo 'MODE: physical port initialization/readback under reset, release before CPU startup; original strict golden/ICB/effective guards; system-scope task SAIF'
echo 'LIMIT: prepare 5min; compile 10min; FF1 15min; encoder 30min; each validation 3min; no synthesis/DC power in this stage'
''']
sources={n:HERE/n for n in ('Prepare.py','SystemTasks.py','TcmInitializer.sv','StageWatch.py')}
sources['TaskActivity.sv']=HERE.parent/'SharedAsic/TaskActivity.sv'
hashes=[]
for index,(name,path) in enumerate(sources.items()):
    data=path.read_bytes().replace(b'\r\n',b'\n')
    marker=f'TPUSOC_SYSTEM_TASK_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_SYSTEM_TASK_HASHES\'\n'+''.join(hashes)+'TPUSOC_SYSTEM_TASK_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
run_stage() {
    local label=$1 limit=$2 log=$3
    shift 3
    python3 -B -u "$tools/StageWatch.py" --label "$label" --limit "$limit" --log "$log" --cwd "$work" -- "$@"
}
if ! run_stage prepare 300 "$work/prepare.log" python3 -B -u "$tools/SystemTasks.py" prepare "$work" --review "$review"; then tail -n 24 "$work/prepare.log"; exit 1; fi
tail -n 2 "$work/prepare.log"
stage=compile_physical_tcm_tasks
if ! run_stage compile 600 "$work/compile.log" "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps -assert svaext \
    +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero +vcs+saif_libcell -f "$work/Task.f" \
    "$work/GateResetInventory.sv" "$work/IcbMirror.sv" "$work/EffectiveDataGuard.sv" \
    "$work/SystemActivity.sv" "$work/SharedTcmGuard.sv" "$tools/TcmInitializer.sv" \
    -top SharedTest -top GateResetInventory -top IcbMirror -top EffectiveDataGuard \
    -top TaskActivity -top SharedTcmGuard -top TcmInitializer -o "$work/simv"; then
    tail -n 35 "$work/compile.log"; exit 1
fi
bundle=$(cat "$work/Bundle.txt"); firmware=$(cat "$work/Firmware.txt")
for task in ff1 encoder; do
    kind=0; limit=1800; vectors="$bundle/Vectors"
    if [[ "$task" == ff1 ]]; then kind=1; limit=900; vectors="$vectors/Ff1_normal"; fi
    stage="simulate_$task"
    if ! run_stage "$stage" "$limit" "$work/$task/run.log" "$work/simv" +INIT_ALL=1 +INIT_PATTERN=2 \
        +RESET_X_LIST="$work/$task/reset_x.txt" +TASK_SAIF="$work/$task/task.saif" \
        +FIRMWARE="$firmware" +VECTORS="$vectors" +KIND="$kind" +LAYERS=1; then
        tail -n 28 "$work/$task/run.log"; exit 1
    fi
    grep -E '^(PASS PHYSICAL_TCM_INIT:|PASS SHARED:|PASS SHARED_TCM_GUARD:|INIT_FINAL:|TASK_ACTIVITY_END:)' "$work/$task/run.log"
    stage="validate_$task"
    if ! run_stage "$stage" 180 "$work/$task/validate.log" python3 -B -u "$tools/SystemTasks.py" validate "$work" --task "$task"; then
        tail -n 24 "$work/$task/validate.log"; exit 1
    fi
    cat "$work/$task/validate.log"
done
echo 'RESULT: SYSTEM_PHYSICAL_TCM_TASK_ACTIVITY_COMPLETE (inspect task records; system power still needs DDC annotation/coverage/X review)'
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode()
out=ROOT/'workspace/Server/tpusoc_system_tasks_20261107_v2.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
