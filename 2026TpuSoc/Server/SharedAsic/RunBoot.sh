#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash GATE_BOOT.sh [COMPLETED_CONE]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS missing'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_gate_boot_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: binary-start reset for diagnosed Word[0] reconvergence, then unchanged mapped-candidate functional tests'
echo 'SCOPE: one Word[0] Q force during reset, released permanently before reset deassertion; retain strict X and golden output checks'
echo 'LIMIT: unit compile 5min/run 20sec; full compile 10min; FF1 10min/seed; single encoder 20min; no synthesis'
# __BOOT_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then "$py" "$tools/PrepareBoot.py" --cone "$1" --out "$work";
else "$py" "$tools/PrepareBoot.py" --out "$work"; fi
compile_case() {
    local name=$1 list=$2 top=$3 limit=$4
    shift 4
    mkdir -p "$work/$name"
    stage="compile_$name"
    echo "RUN: $stage; log=$work/$name/compile.log"
    if ! (cd "$work/$name"; timeout -k 10 "$limit" "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
        -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero \
        -f "$work/$list" "$@" -top "$top" -o simv) > "$work/$name/compile.log" 2>&1; then
        tail -n 55 "$work/$name/compile.log"; exit 1
    fi
}
run_case() {
    local name=$1 binary=$2 seed=$3 limit=$4
    shift 4
    stage="simulate_$name"
    echo "RUN: $stage; log=$work/$name.log"
    local rc=0 status=FAIL
    (cd "$work/$binary"; timeout -k 10 "$limit" ./simv +BOOT_WORD0="$seed" "$@") > "$work/$name.log" 2>&1 || rc=$?
    if [[ "$rc" == 124 || "$rc" == 137 ]]; then status=TIMEOUT;
    elif [[ "$rc" == 0 ]] && grep -q '^PASS ' "$work/$name.log" \
        && grep -q '^BOOT_RESET_VERIFIED:' "$work/$name.log" \
        && grep -q '^BOOT_FINAL: .*released=1 checked=1' "$work/$name.log" \
        && ! grep -Eiq '(Fatal:|Error-\[|FATAL:|FAIL:)' "$work/$name.log"; then
        if [[ "$binary" == full ]] && ! grep -q '^ICB_MIRROR_FINAL: divergence_observed=0' "$work/$name.log"; then status=FAIL;
        else status=PASS; fi
    fi
    printf '%s\t%s\texit=%s\n' "$name" "$status" "$rc" >> "$work/results.tsv"
    echo "BOOT_CASE: $name $status exit=$rc"
    grep -E '^(BOOT_|PASS |ICB_FIRST|ICB_MIRROR_FINAL:|ICB_FINAL_|Fatal:|UNKNOWN_|DIAG_FINAL:)' "$work/$name.log" || true
    if [[ "$status" != PASS ]]; then tail -n 35 "$work/$name.log"; return 1; fi
}
compile_case unit unit.f GateIcbSmoke 300 "$tools/GateIcbSmoke.sv" "$work/UnitResetWordBoot.sv" -top UnitResetWordBoot
run_case unit_seed0 unit 0 20
run_case unit_seed1 unit 1 20
compile_case full full.f SharedTest 600 "$work/FullResetWordBoot.sv" "$tools/IcbMirror.sv" "$tools/GateWatch.sv" -top FullResetWordBoot -top IcbMirror -top GateWatch
bundle=$(cat "$work/Bundle.txt")
functional=$(cat "$work/Functional.txt")
for seed in 0 1; do
    run_case "ff1_seed$seed" full "$seed" 600 +FIRMWARE="$functional/project/Firmware.hex" +VECTORS="$bundle/Vectors/Ff1_normal" +KIND=1 +LAYERS=1
done
run_case encoder_seed0 full 0 1200 +FIRMWARE="$functional/project/Firmware.hex" +VECTORS="$bundle/Vectors" +KIND=0 +LAYERS=1
stage=recheck
"$py" -c 'import sys,json,hashlib; from pathlib import Path; r=json.load(open(sys.argv[1])); assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==s for p,s in r["inputs"].items()), "input changed"' "$work/BootInputs.json"
echo 'BOOT_SUMMARY:'
cat "$work/results.tsv"
echo 'RESULT: PASS BINARY_START_GATE_FUNCTIONAL (explicit reset initial conditions; no unseeded X-start, SDF, formal equivalence or power claim)'
echo "WORK_DIR: $work"
