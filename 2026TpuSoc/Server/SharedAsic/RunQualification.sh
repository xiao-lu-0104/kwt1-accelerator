#!/usr/bin/env bash
set -euo pipefail
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
for bin in "$dc_bin" "$vcs_bin"; do [[ -x "$bin" ]] || { echo "ERROR: tool missing: $bin"; exit 2; }; done
export PATH="$(dirname "$dc_bin"):$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_activity_qualification_20261106_XXXXXX")
tools="$work/tools"
mkdir -p "$tools" "$work/ff1" "$work/encoder" "$work/macro"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: passive valid-data guards; original task stimulus and pattern2 reset/release; raw shared macro smoke; corrected DC activity query'
echo 'LIMIT: prepare 5min; macro compile 3min/run 20sec; read-only DC 8min/task; gate compile 10min; FF1 15min; encoder 30min'
echo 'POWER_SCOPE: no new power number or system-total acceptance; no synthesis or activity override'
# __QUALIFICATION_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
echo "RUN: prepare with progress and 5min timeout; log=$work/runner.log"
timeout -k 10 300 "$py" -u "$tools/PrepareQualification.py" "$work"
source_run=$(cat "$work/Source.txt")
macro_model=$(cat "$work/Macro.txt")
stage=shared_macro_smoke
status=FAIL
echo "RUN: isolated shared SRAM macro smoke; log=$work/macro/run.log"
if (cd "$work/macro"; timeout -k 10 180 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
    +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero -v "$macro_model" \
    "$tools/SharedMacroSmoke.sv" -top SharedMacroSmoke -o simv) > "$work/macro/compile.log" 2>&1; then
    if (cd "$work/macro"; timeout -k 5 20 ./simv) > "$work/macro/run.log" 2>&1 \
        && grep -q '^PASS SHARED_MACRO_SMOKE:' "$work/macro/run.log" \
        && ! grep -Eiq '(Fatal:|FATAL:|Error-\[)' "$work/macro/run.log"; then status=PASS;
    else tail -n 12 "$work/macro/run.log"; fi
else tail -n 16 "$work/macro/compile.log"; fi
printf '%s\n' "$status" > "$work/macro/status.txt"
echo "SHARED_MACRO_CASE: $status"
export TPU_POWER_DDC TPU_STDCELL_DB TPU_SRAM_DB TPU_QUAL_CASE TPU_QUAL_SAIF
TPU_POWER_DDC=$(cat "$work/Ddc.txt")
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
for task in ff1 encoder; do
    stage="clock_$task"; status=FAIL
    TPU_QUAL_CASE="$work/$task"; TPU_QUAL_SAIF="$source_run/$task/task.saif"
    echo "RUN: $stage; log=$work/$task/clock.log"
    if timeout -k 10 480 "$dc_bin" -f "$tools/QualificationClock.tcl" > "$work/$task/clock.log" 2>&1 \
        && grep -q '^QUALIFICATION_CLOCK_COMPLETE:' "$work/$task/clock.log" \
        && ! grep -q '^QUALIFICATION_CLOCK_ERROR:' "$work/$task/clock.log"; then status=PASS;
    else tail -n 12 "$work/$task/clock.log"; fi
    printf '%s\n' "$status" > "$work/$task/clock_status.txt"
    echo "CLOCK_QUERY_CASE: $task $status"
done
stage=compile_effective_guard
echo "RUN: original mapped task plus passive guards; log=$work/compile.log"
if ! (cd "$work"; timeout -k 10 600 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
    -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero -f Task.f \
    "$source_run/GateResetInventory.sv" "$source_run/IcbMirror.sv" "$source_run/GateWatch.sv" \
    "$tools/QualificationWindow.sv" "$work/EffectiveDataGuard.sv" \
    -top SharedTest -top GateResetInventory -top IcbMirror -top GateWatch \
    -top TaskActivity -top EffectiveDataGuard -o simv) > "$work/compile.log" 2>&1; then
    tail -n 22 "$work/compile.log"; exit 1
fi
bundle=$(cat "$source_run/Bundle.txt")
functional=$(cat "$source_run/Functional.txt")
for task in ff1 encoder; do
    kind=0; limit=1800; vectors="$bundle/Vectors"
    if [[ "$task" == ff1 ]]; then kind=1; limit=900; vectors="$vectors/Ff1_normal"; fi
    stage="simulate_$task"; rc=0
    echo "RUN: $stage; log=$work/$task/run.log"
    (cd "$work"; timeout -k 10 "$limit" ./simv +INIT_ALL=1 +INIT_PATTERN=2 \
        +RESET_X_LIST="$work/$task/reset_x.txt" +FIRMWARE="$functional/project/Firmware.hex" \
        +VECTORS="$vectors" +KIND="$kind" +LAYERS=1) > "$work/$task/run.log" 2>&1 || rc=$?
    status=FAIL
    if [[ "$rc" == 0 ]] && grep -q '^PASS EFFECTIVE_DATA_GUARD:' "$work/$task/run.log" \
        && grep -q '^PASS SHARED:' "$work/$task/run.log" \
        && ! grep -Eiq '(Fatal:|FATAL:|Error-\[)' "$work/$task/run.log"; then status=PASS;
    else tail -n 16 "$work/$task/run.log"; fi
    printf '%s\n' "$status" > "$work/$task/status.txt"
    echo "EFFECTIVE_GUARD_CASE: $task $status exit=$rc"
done
stage=summary
"$py" "$tools/SummarizeQualification.py" "$work"
echo 'RESULT: ACTIVITY_QUALIFICATION_COLLECTION_COMPLETE (individual statuses explicit; no final power acceptance)'
echo "WORK_DIR: $work"
