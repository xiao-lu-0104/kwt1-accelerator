#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash SHARED_PROBE.sh [FAILED_GATE_V1_RUN]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS missing'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_gate_probe_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: strict X checks; passive ICB RTL mirror; baseline vs candidate; diagnostic Bus replacement'
echo 'LIMIT: compile 10min/variant; FF1 15min/variant; no synthesis/STA/power claims'
# __GATE_PROBE_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then
    "$py" "$tools/PrepareProbe.py" --gate "$1" --out "$work" --tools-sha __GATE_V1_TOOLS_SHA__
else
    "$py" "$tools/PrepareProbe.py" --out "$work" --tools-sha __GATE_V1_TOOLS_SHA__
fi
bundle=$(cat "$work/Bundle.txt")
functional=$(cat "$work/Functional.txt")
for mode in baseline candidate bus_rtl_control; do
    mkdir -p "$work/$mode"
    stage="compile_$mode"
    echo "RUN: $stage; log=$work/$mode/compile.log"
    if ! (cd "$work/$mode"; timeout -k 10 600 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
        -assert svaext +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero \
        -f "$work/$mode.f" "$tools/GateWatch.sv" "$tools/IcbMirror.sv" \
        -top SharedTest -top GateWatch -top IcbMirror -o simv) > "$work/$mode/compile.log" 2>&1; then
        tail -n 60 "$work/$mode/compile.log"; exit 1
    fi
    stage="simulate_$mode"
    echo "RUN: $stage; log=$work/$mode/ff1.log"
    status=FAIL
    if (cd "$work/$mode"; timeout -k 15 900 ./simv +FIRMWARE="$functional/project/Firmware.hex" \
        +VECTORS="$bundle/Vectors/Ff1_normal" +KIND=1 +LAYERS=1) > "$work/$mode/ff1.log" 2>&1; then
        if grep -q '^PASS SHARED:' "$work/$mode/ff1.log" && ! grep -Eiq '(Error-\[|Fatal:|FATAL:|FAIL:|Assertion.*failed)' "$work/$mode/ff1.log"; then status=PASS; fi
    fi
    printf '%s\t%s\n' "$mode" "$status" >> "$work/results.tsv"
    echo "PROBE_CASE: $mode $status"
    grep -E '^(ICB_FIRST|ICB_INPUT:|ICB_BUS_INPUT:|ICB_ACTUAL:|ICB_EXPECTED:|ICB_MIRROR_FINAL:|PASS SHARED:|DIAG_FINAL:|DIAG_MAILBOX:|Fatal:|UNKNOWN_)' "$work/$mode/ff1.log" || true
    if [[ "$status" != PASS ]]; then tail -n 12 "$work/$mode/ff1.log"; fi
done
stage=recheck
"$py" -c 'import sys,json,hashlib; from pathlib import Path; r=json.load(open(sys.argv[1])); assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==s for p,s in r["inputs"].items()), "probe input changed"' "$work/ProbeInputs.json"
echo 'PROBE_SUMMARY:'
cat "$work/results.tsv"
echo 'RESULT: GATE_PROBE_COMPLETE (hybrid is diagnostic only; failure not waived)'
echo "WORK_DIR: $work"
