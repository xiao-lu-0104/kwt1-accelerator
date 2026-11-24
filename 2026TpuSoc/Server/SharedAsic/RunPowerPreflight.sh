#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash POWER_PREFLIGHT.sh [PASSED_INVENTORY]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
for bin in "$dc_bin" "$vcs_bin"; do [[ -x "$bin" ]] || { echo "ERROR: tool not found: $bin"; exit 2; }; done
export PATH="$(dirname "$dc_bin"):$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_power_preflight_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools" "$work/smoke"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'SCOPE: frozen mapped candidate+original TT libraries; area units/LEF, installed power-command help and 4-FF native-SAIF smoke only'
echo 'LIMIT: read-only DC 8min; SAIF smoke compile 3min/run 20sec; no synthesis or full-task rerun; no power value claimed'
# __POWER_PREFLIGHT_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then "$py" "$tools/PreparePower.py" --inventory "$1" --out "$work";
else "$py" "$tools/PreparePower.py" --out "$work"; fi
export TPU_POWER_OUT="$work" TPU_POWER_DDC TPU_STDCELL_DB TPU_SRAM_DB
TPU_POWER_DDC=$(cat "$work/Ddc.txt")
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
stage=dc_read_only
echo "RUN: read-only checkpoint/units/capabilities; log=$work/dc.log"
if ! (cd "$work"; timeout -k 10 480 "$dc_bin" -f "$tools/PowerPreflight.tcl") > "$work/dc.log" 2>&1; then
    tail -n 65 "$work/dc.log"; exit 1
fi
if ! grep -q '^POWER_PREFLIGHT_DDC_COMPLETE:' "$work/dc.log" || grep -q '^POWER_PREFLIGHT_ERROR:' "$work/dc.log"; then
    tail -n 65 "$work/dc.log"; exit 1
fi
grep '^POWER_PREFLIGHT_DDC_COMPLETE:' "$work/dc.log"
stage=saif_smoke_compile
echo "RUN: 4-FF native-SAIF compile; log=$work/smoke/compile.log"
smoke_status=COMPILE_FAIL
if (cd "$work/smoke"; timeout -k 10 180 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
    +notimingcheck +delay_mode_zero +vcs+saif_libcell -f "$work/Smoke.f" "$tools/SaifSmoke.sv" -top SaifSmoke -o simv) > "$work/smoke/compile.log" 2>&1; then
    stage=saif_smoke_run
    rc=0
    (cd "$work/smoke"; timeout -k 5 20 ./simv) > "$work/smoke/run.log" 2>&1 || rc=$?
    smoke_status=SIM_FAIL
    if [[ "$rc" == 124 || "$rc" == 137 ]]; then smoke_status=TIMEOUT;
    elif [[ "$rc" == 0 ]] && grep -q '^PASS SAIF_SMOKE:' "$work/smoke/run.log" \
        && ! grep -Eiq '(Fatal:|FATAL:|Error-\[)' "$work/smoke/run.log"; then smoke_status=PASS; fi
    tail -n 16 "$work/smoke/run.log"
else tail -n 35 "$work/smoke/compile.log"; fi
printf '%s\n' "$smoke_status" > "$work/smoke_status.txt"
stage=summary
"$py" "$tools/SummarizePower.py" "$work"
echo 'RESULT: POWER_PREFLIGHT_COMPLETE (metadata/capability only; actual full-task power still pending)'
echo "WORK_DIR: $work"
