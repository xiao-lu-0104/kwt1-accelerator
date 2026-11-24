#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash SHARED_GATE.sh [COMPLETED_REPORT_DIR]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
for tool in "$dc_bin" "$vcs_bin"; do [[ -x "$tool" ]] || { echo "ERROR: tool not found $tool"; exit 2; }; done
work=$(mktemp -d "$HOME/soc/tpusoc_shared_gate_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'SCOPE: audit all outside additions, actual mapped NICE/TPU/ICB + vendor SRAM, original RTL CPU/TCM'
echo 'MODE: functional gate simulation, no SDF, macro timing checks disabled; no power/equivalence claim'
echo 'LIMIT: buffer audit 5min, VCS compile 10min, FF1/encoder simulation 30min each'
# __SHARED_GATE_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then
    "$py" "$tools/PrepareGate.py" --report "$1" --out "$work" --report-tools-sha __REPORT_TOOLS_SHA__ --asic-tools-sha __ASIC_TOOLS_SHA__
else
    "$py" "$tools/PrepareGate.py" --out "$work" --report-tools-sha __REPORT_TOOLS_SHA__ --asic-tools-sha __ASIC_TOOLS_SHA__
fi
export TPU_STDCELL_DB TPU_SRAM_DB TPU_GATE_WORK="$work"
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
export PATH="$(dirname "$dc_bin"):$(dirname "$vcs_bin"):$PATH"
stage=buffer_function_audit
if ! (cd "$work"; timeout -k 10 300 "$dc_bin" -f "$tools/AuditCells.tcl") > "$work/audit.log" 2>&1; then
    tail -n 55 "$work/audit.log"; exit 1
fi
if ! grep -q '^BUFFER_FUNCTION_AUDIT_COMPLETE:' "$work/audit.log" || grep -Eq '^(Error:|BUFFER_AUDIT_ERROR:)' "$work/audit.log"; then
    tail -n 55 "$work/audit.log"; exit 1
fi
grep -E '^(ADDED_CELL_FUNCTION:|BUFFER_FUNCTION_AUDIT_COMPLETE:)' "$work/audit.log"
if [[ $(cat "$work/OutsideAdditionsOnly.txt") != 1 || $(cat "$work/BuffersOnly.txt") != 1 ]]; then
    echo 'SCOPE_STATUS: REQUIRES_NONBUFFER_OR_REMOVAL_REVIEW'; exit 1
fi
echo 'SCOPE_STATUS: ORIGINAL_OUTSIDE_REFERENCES_PRESERVED; ALL_OUTSIDE_ADDITIONS_ARE_LIBRARY_BUFFERS'
if [[ $(cat "$work/ModelsReady.txt") != 1 ]]; then
    echo 'RESULT: MODEL_INPUT_REQUIRED (buffer audit complete; gate simulation not run)'
    echo "WORK_DIR: $work"; exit 0
fi
stage=gate_compile
echo "RUN: gate compile; log=$work/compile.log"
if ! (cd "$work"; timeout -k 10 600 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
    -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck -f Gate.f -top SharedTest -o simv) > "$work/compile.log" 2>&1; then
    tail -n 60 "$work/compile.log"; exit 1
fi
bundle=$(cat "$work/Bundle.txt")
functional=$(cat "$work/Functional.txt")
for mode in ff1 encoder; do
    kind=0; vectors="$bundle/Vectors"
    if [[ "$mode" == ff1 ]]; then kind=1; vectors="$vectors/Ff1_normal"; fi
    stage="simulate_$mode"
    echo "RUN: $mode gate simulation; log=$work/$mode.log"
    if ! (cd "$work"; timeout -k 15 1800 ./simv +FIRMWARE="$functional/project/Firmware.hex" +VECTORS="$vectors" +KIND="$kind" +LAYERS=1) > "$work/$mode.log" 2>&1; then
        tail -n 55 "$work/$mode.log"; exit 1
    fi
    if ! grep -q '^PASS SHARED:' "$work/$mode.log" || grep -Eiq '(Error-\[|Fatal:|FATAL:|FAIL:|Assertion.*failed)' "$work/$mode.log"; then
        tail -n 55 "$work/$mode.log"; exit 1
    fi
    grep '^PASS SHARED:' "$work/$mode.log"
done
stage=recheck
"$py" -c 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from PrepareGate import recheck_gate; recheck_gate(Path(sys.argv[2]))' "$tools" "$work"
sha256sum "$work/candidate.v" > "$work/candidate_sha256.txt"
stage=complete
echo 'RESULT: PASS SHARED_GATE_FUNCTIONAL (FF1+single encoder; vendor cells and SRAM; no SDF/formal equivalence/power)'
echo "WORK_DIR: $work"
