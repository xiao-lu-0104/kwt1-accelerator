"""Build a bounded passive encoder write-X diagnosis; preserve all previous runs."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
old="$HOME/soc/tpusoc_system_tasks_20261106_ZBysEH"
[[ -s "$old/encoder/run.log" ]] || { echo 'ERROR: prior failed encoder evidence required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS not found'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_encoder_write_trace_20261107_XXXXXX")
tools="$work/tools"; mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: ENCODER_TRACE_FAILED stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: passive write/PC/GPR trace; preserve original firmware/RTL/golden vectors/strict macro guard; do not rerun FF1'
echo 'LIMIT: verify 3min, compile 5min, reproduce 5min, summarize 3min; diagnostic only, no power acceptance'
''']
hashes=[]
for index,name in enumerate(('Prepare.py','EncoderWriteDiagnostic.py','CpuWriteTrace.sv','StageWatch.py')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n'); marker=f'TPUSOC_WRITE_TRACE_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_WRITE_TRACE_HASHES\'\n'+''.join(hashes)+'TPUSOC_WRITE_TRACE_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
run_stage() {
    local label=$1 limit=$2 log=$3
    shift 3
    python3 -B -u "$tools/StageWatch.py" --label "$label" --limit "$limit" --log "$log" --cwd "$work" -- "$@"
}
if ! run_stage prepare 180 "$work/prepare.log" python3 -B -u "$tools/EncoderWriteDiagnostic.py" prepare "$work" --task-run "$old"; then
    tail -n 20 "$work/prepare.log"; exit 1
fi
cat "$work/prepare.log"
stage=compile_passive_trace
if ! run_stage compile_trace 300 "$work/compile.log" "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps -assert svaext \
    +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero +vcs+saif_libcell -f "$old/Task.f" \
    "$old/GateResetInventory.sv" "$old/IcbMirror.sv" "$old/EffectiveDataGuard.sv" \
    "$old/SystemActivity.sv" "$old/SharedTcmGuard.sv" "$old/tools/TcmInitializer.sv" "$tools/CpuWriteTrace.sv" \
    -top SharedTest -top GateResetInventory -top IcbMirror -top EffectiveDataGuard -top TaskActivity \
    -top SharedTcmGuard -top TcmInitializer -top CpuWriteTrace -o "$work/simv"; then
    tail -n 28 "$work/compile.log"; exit 1
fi
bundle=$(cat "$old/Bundle.txt"); firmware=$(cat "$old/Firmware.txt")
stage=reproduce_encoder_unknown_write
rc=0
run_stage reproduce_encoder 300 "$work/run.log" "$work/simv" +INIT_ALL=1 +INIT_PATTERN=2 \
    +RESET_X_LIST="$work/reset_x.txt" +TASK_SAIF="$work/diagnostic.saif" \
    +FIRMWARE="$firmware" +VECTORS="$bundle/Vectors" +KIND=0 +LAYERS=1 || rc=$?
if [[ "$rc" == 124 ]]; then tail -n 25 "$work/run.log"; exit 1; fi
stage=summarize_diagnostic
if ! run_stage summarize_diagnostic 180 "$work/summary.log" python3 -B -u "$tools/EncoderWriteDiagnostic.py" finish "$work"; then
    tail -n 22 "$work/run.log"; tail -n 16 "$work/summary.log"; exit 1
fi
cat "$work/summary.log"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode()
out=ROOT/'workspace/Server/tpusoc_encoder_write_trace_20261107_v1.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
