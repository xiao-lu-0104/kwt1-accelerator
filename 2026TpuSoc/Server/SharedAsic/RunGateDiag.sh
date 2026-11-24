#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash SHARED_GATE_DIAG.sh [FAILED_GATE_V1_RUN]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS not found'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_gate_diag_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: same saved netlist and test; passive trace; compare default delays vs +delay_mode_zero'
echo 'LIMIT: compile 10min/variant; default reproduction 5min; zero-delay tests 30min/task'
# __GATE_DIAG_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then
    "$py" "$tools/PrepareGateDiag.py" --previous "$1" --out "$work" --tools-sha __GATE_V1_TOOLS_SHA__
else
    "$py" "$tools/PrepareGateDiag.py" --out "$work" --tools-sha __GATE_V1_TOOLS_SHA__
fi
bundle=$(cat "$work/Bundle.txt")
functional=$(cat "$work/Functional.txt")
compile_variant() {
    local name=$1 list=$2
    shift 2
    mkdir -p "$work/$name"
    stage="compile_$name"
    echo "RUN: $stage; log=$work/$name/compile.log"
    if ! (cd "$work/$name"; timeout -k 10 600 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
        -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck "$@" \
        -f "$work/$list" "$tools/GateWatch.sv" -top SharedTest -top GateWatch -o simv) > "$work/$name/compile.log" 2>&1; then
        tail -n 55 "$work/$name/compile.log"; return 1
    fi
}
run_variant() {
    local variant=$1 name=$2 kind=$3 vectors=$4 limit=$5
    stage="simulate_${variant}_${name}"
    echo "RUN: $stage; log=$work/$variant/$name.log"
    if (cd "$work/$variant"; timeout -k 15 "$limit" ./simv +FIRMWARE="$functional/project/Firmware.hex" \
        +VECTORS="$vectors" +KIND="$kind" +LAYERS=1) > "$work/$variant/$name.log" 2>&1; then
        if grep -q '^PASS SHARED:' "$work/$variant/$name.log" && ! grep -Eiq '(Error-\[|Fatal:|FATAL:|FAIL:|Assertion.*failed)' "$work/$variant/$name.log"; then
            grep '^PASS SHARED:' "$work/$variant/$name.log"
            return 0
        fi
    fi
    tail -n 38 "$work/$variant/$name.log"
    return 1
}
compile_variant default Gate.f
if run_variant default ff1 1 "$bundle/Vectors/Ff1_normal" 300; then
    echo 'DEFAULT_DELAY_REPRODUCTION: PASS_WITH_OBSERVER (investigate scheduling sensitivity)'
else
    echo 'DEFAULT_DELAY_REPRODUCTION: FAIL (retained for comparison)'
fi
compile_variant zero Gate.f +delay_mode_zero
zero_pass=1
if ! run_variant zero ff1 1 "$bundle/Vectors/Ff1_normal" 1800; then zero_pass=0; fi
if [[ "$zero_pass" == 1 ]]; then
    if ! run_variant zero encoder 0 "$bundle/Vectors" 1800; then zero_pass=0; fi
fi
if [[ "$zero_pass" == 0 ]]; then
    compile_variant reference Reference.f +delay_mode_zero +define+TPU_SRAM_MODEL
    if run_variant reference ff1 1 "$bundle/Vectors/Ff1_normal" 1800; then
        echo 'RTL_CONTROL_WITH_SAME_LIBRARIES: PASS'
    else
        echo 'RTL_CONTROL_WITH_SAME_LIBRARIES: FAIL'
    fi
fi
stage=recheck
"$py" -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from PrepareGateDiag import recheck; recheck(Path(sys.argv[2]))' "$tools" "$work"
stage=complete
if [[ "$zero_pass" == 1 ]]; then
    echo 'RESULT: PASS GATE_ZERO_DELAY_FUNCTIONAL (FF1+encoder; all model delays zero; no SDF/STA/power/equivalence claim)'
else
    echo 'RESULT: GATE_DIAGNOSTICS_COMPLETE (functional failure unresolved; inspect traces and RTL control)'
fi
echo "WORK_DIR: $work"
