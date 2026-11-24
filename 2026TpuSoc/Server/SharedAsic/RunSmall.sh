#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash GATE_SMALL.sh [COMPLETED_PROBE]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS missing'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_gate_small_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: actual DFF with/without SRAM model; isolated mapped ICB; corrected passive mirror'
echo 'LIMIT: compile 5min/case; small units 20sec; full diagnostic 180sec; no synthesis'
# __SMALL_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then
    "$py" "$tools/PrepareSmall.py" --probe "$1" --out "$work"
else
    "$py" "$tools/PrepareSmall.py" --out "$work"
fi
bundle=$(cat "$work/Bundle.txt")
functional=$(cat "$work/Functional.txt")
run_case() {
    local name=$1 list=$2 top=$3 limit=$4
    shift 4
    mkdir -p "$work/$name"
    stage="compile_$name"
    echo "RUN: $stage; log=$work/$name/compile.log"
    if ! (cd "$work/$name"; timeout -k 10 300 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
        -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero \
        -f "$work/$list" "$@" -top "$top" -o simv) > "$work/$name/compile.log" 2>&1; then
        tail -n 45 "$work/$name/compile.log"; return 1
    fi
    stage="simulate_$name"
    echo "RUN: $stage; log=$work/$name/run.log"
    status=FAIL
    rc=0
    (cd "$work/$name"; timeout -k 5 "$limit" ./simv +FIRMWARE="$functional/project/Firmware.hex" \
        +VECTORS="$bundle/Vectors/Ff1_normal" +KIND=1 +LAYERS=1) > "$work/$name/run.log" 2>&1 || rc=$?
    if [[ "$rc" == 124 || "$rc" == 137 ]]; then status=TIMEOUT;
    elif [[ "$rc" == 0 ]] && grep -q '^PASS ' "$work/$name/run.log" && ! grep -Eiq '(Fatal:|Error-\[|FATAL:|FAIL:)' "$work/$name/run.log"; then status=PASS; fi
    printf '%s\t%s\texit=%s\n' "$name" "$status" "$rc" >> "$work/results.tsv"
    echo "SMALL_CASE: $name $status exit=$rc"
    if [[ "$name" == full ]]; then
        grep -E '^(ICB_FIRST|ICB_SIZE:|ICB_INPUT:|ICB_BUS_INPUT:|ICB_ACTUAL:|ICB_EXPECTED:|ICB_FINAL_|ICB_MIRROR_FINAL:|Fatal:|UNKNOWN_|PASS SHARED:)' "$work/$name/run.log" || true
        tail -n 14 "$work/$name/run.log"
    else tail -n 14 "$work/$name/run.log"; fi
}
run_case cell_std cell_std.f GateCellSmoke 20 "$tools/GateCellSmoke.sv"
run_case cell_sram cell_sram.f GateCellSmoke 20 "$tools/GateCellSmoke.sv"
run_case icb icb.f GateIcbSmoke 20 "$tools/GateIcbSmoke.sv"
run_case full full.f SharedTest 180 "$tools/GateWatch.sv" "$tools/IcbMirror.sv" -top GateWatch -top IcbMirror
stage=recheck
"$py" -c 'import sys,json,hashlib; from pathlib import Path; r=json.load(open(sys.argv[1])); assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==s for p,s in r["inputs"].items()), "input changed"' "$work/SmallInputs.json"
echo 'SMALL_SUMMARY:'
cat "$work/results.tsv"
echo 'RESULT: GATE_SMALL_DIAGNOSTICS_COMPLETE (diagnostic status only; inspect individual cases)'
echo "WORK_DIR: $work"
