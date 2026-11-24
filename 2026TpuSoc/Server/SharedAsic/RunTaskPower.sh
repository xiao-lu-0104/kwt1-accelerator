#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash TASK_POWER.sh [PASSED_PREFLIGHT]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
for bin in "$dc_bin" "$vcs_bin"; do [[ -x "$bin" ]] || { echo "ERROR: tool not found: $bin"; exit 2; }; done
export PATH="$(dirname "$dc_bin"):$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_task_power_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools" "$work/ff1" "$work/encoder"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'SCOPE: frozen accelerator+private SRAM estimate; CPU/interconnect/shared SRAM remain separate pending components'
echo 'MODE: same pattern2 reset/release and strict golden tests; passive full-task SAIF; no synthesis or constraint changes'
echo 'LIMIT: compile 10min; FF1 15min; encoder 30min; annotated DC 10min/task'
# __TASK_POWER_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then "$py" "$tools/PrepareTaskPower.py" --preflight "$1" --out "$work";
else "$py" "$tools/PrepareTaskPower.py" --out "$work"; fi
stage=compile
echo "RUN: compile mapped task with native SAIF; log=$work/compile.log"
if ! (cd "$work"; timeout -k 10 600 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
    -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero +vcs+saif_libcell \
    -f Task.f "$work/GateResetInventory.sv" "$work/IcbMirror.sv" "$work/GateWatch.sv" \
    "$tools/TaskActivity.sv" -top SharedTest -top GateResetInventory -top IcbMirror -top GateWatch \
    -top TaskActivity -o simv) > "$work/compile.log" 2>&1; then
    tail -n 65 "$work/compile.log"; exit 1
fi
bundle=$(cat "$work/Bundle.txt")
functional=$(cat "$work/Functional.txt")
for name in ff1 encoder; do
    kind=0; limit=1800; vectors="$bundle/Vectors"
    if [[ "$name" == ff1 ]]; then kind=1; limit=900; vectors="$vectors/Ff1_normal"; fi
    stage="simulate_$name"
    echo "RUN: $stage; log=$work/$name/run.log"
    rc=0
    (cd "$work"; timeout -k 10 "$limit" ./simv +INIT_ALL=1 +INIT_PATTERN=2 \
        +RESET_X_LIST="$work/$name/reset_x.txt" +TASK_SAIF="$work/$name/task.saif" \
        +FIRMWARE="$functional/project/Firmware.hex" +VECTORS="$vectors" +KIND="$kind" +LAYERS=1) \
        > "$work/$name/run.log" 2>&1 || rc=$?
    if [[ "$rc" != 0 ]]; then tail -n 65 "$work/$name/run.log"; exit 1; fi
    grep -E '^(TASK_ACTIVITY_|PASS SHARED:|INIT_FINAL:|ICB_MIRROR_FINAL:)' "$work/$name/run.log" || true
    "$py" "$tools/SummarizeTaskPower.py" "$work" --check-activity "$name"
done
export TPU_POWER_DDC TPU_STDCELL_DB TPU_SRAM_DB TPU_TASK_CASE TPU_TASK_SAIF
TPU_POWER_DDC=$(cat "$work/Ddc.txt")
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
for name in ff1 encoder; do
    stage="annotated_power_$name"
    TPU_TASK_CASE="$work/$name"; TPU_TASK_SAIF="$work/$name/task.saif"
    echo "RUN: $stage; log=$work/$name/dc.log"
    status=FAIL
    if (cd "$work/$name"; timeout -k 10 600 "$dc_bin" -f "$tools/TaskPower.tcl") > "$work/$name/dc.log" 2>&1 \
        && grep -q '^TASK_POWER_DDC_COMPLETE:' "$work/$name/dc.log" \
        && ! grep -q '^TASK_POWER_ERROR:' "$work/$name/dc.log"; then status=PASS;
    else tail -n 65 "$work/$name/dc.log"; fi
    printf '%s\n' "$status" > "$work/$name/dc_status.txt"
    echo "ANNOTATED_POWER_TOOL_STATUS: $name $status"
done
stage=summary
"$py" "$tools/SummarizeTaskPower.py" "$work"
echo 'RESULT: TASK_POWER_COLLECTION_COMPLETE (individual tool status and coverage/X review explicit; system total pending)'
echo "WORK_DIR: $work"
