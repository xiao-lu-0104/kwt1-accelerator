#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash GATE_INVENTORY.sh [FAILED_BOOT]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS missing'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_gate_inventory_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: reset-X inventory, earliest known-to-X controls, explicit binary power-up comparisons on original mapped accelerator'
echo 'SCOPE: CPU and SRAM arrays not directly initialized; mapped FF Q initial conditions released after one reset clock; strict X/golden comparisons retained'
echo 'LIMIT: compile 10min; reference failure 180sec; FF1 10min/pattern; encoder 20min; no synthesis'
# __INVENTORY_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then "$py" "$tools/PrepareInventory.py" --boot "$1" --out "$work";
else "$py" "$tools/PrepareInventory.py" --out "$work"; fi
stage=compile
echo "RUN: compile; log=$work/compile.log"
if ! (cd "$work"; timeout -k 10 600 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
    -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero -f full.f \
    "$work/GateResetInventory.sv" "$tools/IcbMirror.sv" "$tools/GateWatch.sv" \
    -top SharedTest -top GateResetInventory -top IcbMirror -top GateWatch -o simv) > "$work/compile.log" 2>&1; then
    tail -n 65 "$work/compile.log"; exit 1
fi
bundle=$(cat "$work/Bundle.txt")
functional=$(cat "$work/Functional.txt")
run_case() {
    local name=$1 all=$2 pattern=$3 kind=$4 limit=$5
    local vectors="$bundle/Vectors" status=FAIL rc=0
    if [[ "$kind" == 1 ]]; then vectors="$vectors/Ff1_normal"; fi
    stage="simulate_$name"
    echo "RUN: $stage; log=$work/$name.log"
    (cd "$work"; timeout -k 10 "$limit" ./simv +INIT_ALL="$all" +INIT_PATTERN="$pattern" \
        +RESET_X_LIST="$work/$name.reset_x.txt" +FIRMWARE="$functional/project/Firmware.hex" \
        +VECTORS="$vectors" +KIND="$kind" +LAYERS=1) > "$work/$name.log" 2>&1 || rc=$?
    if [[ "$rc" == 124 || "$rc" == 137 ]]; then status=TIMEOUT;
    elif [[ "$rc" == 0 ]] && grep -q '^PASS SHARED:' "$work/$name.log" \
        && grep -q '^INIT_FINAL: .*released=1 checked=1' "$work/$name.log" \
        && grep -q '^ICB_MIRROR_FINAL: divergence_observed=0' "$work/$name.log" \
        && ! grep -Eiq '(Fatal:|Error-\[|FATAL:|FAIL:)' "$work/$name.log"; then status=PASS; fi
    printf '%s\t%s\texit=%s\n' "$name" "$status" "$rc" >> "$work/results.tsv"
    echo "INVENTORY_CASE: $name $status exit=$rc"
    grep -E '^(INIT_|RESET_INVENTORY:|RESET_CONTROL_QX:|NEW_CONTROL_QX:|PASS SHARED:|ICB_FIRST|ICB_MIRROR_FINAL:|ICB_FINAL_|Fatal:|UNKNOWN_|DIAG_FINAL:)' "$work/$name.log" || true
    if [[ "$status" != PASS ]]; then tail -n 12 "$work/$name.log"; fi
}
run_case word0_reference 0 0 1 180
for pattern in 0 1 2; do run_case "ff1_all_pattern$pattern" 1 "$pattern" 1 600; done
if [[ $(grep -Ec '^ff1_all_pattern[012][[:space:]]+PASS' "$work/results.tsv") == 3 ]]; then
    run_case encoder_all_pattern2 1 2 0 1200
else echo 'ENCODER_SKIPPED: binary-start FF1 did not pass every pattern'; fi
stage=recheck
"$py" -c 'import sys,json,hashlib; from pathlib import Path; r=json.load(open(sys.argv[1])); assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==s for p,s in r["inputs"].items()), "input changed"' "$work/InventoryInputs.json"
echo 'INVENTORY_SUMMARY:'
cat "$work/results.tsv"
echo 'RESULT: GATE_INVENTORY_COMPLETE (individual results and initial conditions explicit; no unseeded/formal/SDF/power acceptance)'
echo "WORK_DIR: $work"
