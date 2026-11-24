#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
build=$(mktemp -d /tmp/tpusoc_system_base_XXXXXX)
echo "LOCAL_SYSTEM_BASE_BUILD: $build"
cp "$here/TcmMacro.sv" "$here/TcmContract.sv" "$build/"
python3 "$repo/Server/SharedAsic/TestQualification.py" --fixtures "$build"
cp "$repo/workspace/Backend/Local20261102Soc30Tpu150/Sources/e203_hbirdv2/rtl/e203/general/sirv_sim_ram.v" "$build/"
cd "$build"
if ! verilator --binary --timing -Wno-fatal --top-module TcmContract \
    TcmMacro.sv TcmContract.sv MacroFixture.sv sirv_sim_ram.v > build.log 2>&1; then
    tail -n 30 build.log; exit 1
fi
./obj_dir/VTcmContract > good.log 2>&1
grep '^PASS TCM_' good.log
if (ulimit -c 0; ./obj_dir/VTcmContract +BAD_MASK) > bad.log 2>&1; then
    echo 'ERROR: reversed physical bit mask accepted'; exit 1
fi
grep -q 'TCM_READ_CONTRACT' bad.log
echo 'PASS LOCAL_TCM_NEGATIVE: reversed physical WEN rejected; local contract fixture only'
python3 - "$here/StageWatch.py" "$build" <<'PY'
import subprocess,sys,time
from pathlib import Path
watch,build=sys.argv[1],Path(sys.argv[2])
start=time.monotonic()
result=subprocess.run([sys.executable,watch,'--label','timeout_test','--limit','0.2','--log',str(build/'timeout.log'),
    '--cwd',str(build),'--',sys.executable,'-c','import time; print("started",flush=True); time.sleep(30)'],capture_output=True,text=True)
assert result.returncode==124 and time.monotonic()-start<5,result.stdout+result.stderr
result=subprocess.run([sys.executable,watch,'--label','exit_test','--limit','5','--log',str(build/'exit.log'),
    '--cwd',str(build),'--',sys.executable,'-c','raise SystemExit(7)'],capture_output=True,text=True)
assert result.returncode==7,result.stdout+result.stderr
print('PASS LOCAL_STAGE_WATCH: timeout terminates its own process group; tool failures retained')
PY
python3 "$here/LocalPlatform.py" "$build"
if ! verilator --lint-only --timing -Wno-fatal --top-module e203_cpu_top -f CpuLint.f \
    MacroFixture.sv PrivateMacroFixture.sv > cpu_lint.log 2>&1; then
    tail -n 35 cpu_lint.log; exit 1
fi
echo 'PASS LOCAL_CPU_INTERFACE_LINT: local comparison platform at 256KiB+256KiB and current RTL; not server frozen-netlist synthesis'
