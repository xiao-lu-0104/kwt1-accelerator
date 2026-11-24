#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash GATE_CONE.sh [COMPLETED_PROBE]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS missing'; exit 2; }
export PATH="$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_gate_cone_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: isolated feedback DFF and mapped ICB; stable combinational X source and FF D/Q traces'
echo 'LIMIT: compile 5min/case; simulate 20sec/case; no synthesis or full-system run'
# __CONE_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then
    "$py" "$tools/PrepareCone.py" --probe "$1" --out "$work"
else
    "$py" "$tools/PrepareCone.py" --out "$work"
fi
run_case() {
    local name=$1 list=$2 top=$3
    shift 3
    mkdir -p "$work/$name"
    stage="compile_$name"
    echo "RUN: $stage; log=$work/$name/compile.log"
    if ! (cd "$work/$name"; timeout -k 10 300 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
        +define+FPGA+FPGA_SOURCE +notimingcheck +delay_mode_zero -f "$work/$list" "$@" -top "$top" -o simv) > "$work/$name/compile.log" 2>&1; then
        tail -n 50 "$work/$name/compile.log"; return 1
    fi
    stage="simulate_$name"
    echo "RUN: $stage; log=$work/$name/run.log"
    local status=FAIL rc=0
    (cd "$work/$name"; timeout -k 5 20 ./simv) > "$work/$name/run.log" 2>&1 || rc=$?
    if [[ "$rc" == 124 || "$rc" == 137 ]]; then status=TIMEOUT;
    elif [[ "$rc" == 0 ]] && grep -q '^PASS ' "$work/$name/run.log" && ! grep -Eiq '(Fatal:|Error-\[|FATAL:|FAIL:)' "$work/$name/run.log"; then status=PASS; fi
    printf '%s\t%s\texit=%s\n' "$name" "$status" "$rc" >> "$work/results.tsv"
    echo "CONE_CASE: $name $status exit=$rc"
    tail -n 45 "$work/$name/run.log"
}
run_case feedback cell.f GateFeedbackSmoke "$tools/GateFeedbackSmoke.sv"
run_case real real.f GateIcbSmoke "$tools/GateIcbSmoke.sv" "$work/IcbConeWatch.sv" -top IcbConeWatch
run_case functional real.f GateIcbSmoke +define+functional "$tools/GateIcbSmoke.sv" "$work/IcbConeWatch.sv" -top IcbConeWatch
run_case nba_diagnostic diagnostic.f GateIcbSmoke "$tools/GateIcbSmoke.sv" "$work/IcbConeWatch.sv" -top IcbConeWatch
stage=model_evidence
"$py" - "$work" <<'CONE_MODEL_EVIDENCE'
import json,re,sys
from pathlib import Path
p=Path(sys.argv[1]); models=json.loads((p/'BusModels.json').read_text()); refs=set()
for case in ('real','functional','nba_diagnostic'):
    for line in (p/case/'run.log').read_text(errors='replace').splitlines():
        m=re.search(r'CELL_XSOURCE: ref=(\w+)',line)
        if m: refs.add(m[1])
for ref in sorted(refs):
    print('XSOURCE_MODEL_BEGIN:',ref)
    print(re.split(r'\bspecify\b',models[ref],maxsplit=1)[0])
    print('XSOURCE_MODEL_END:',ref)
r=json.loads((p/'ConeInputs.json').read_text())
import hashlib
assert all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==s for name,s in r['inputs'].items()),'input changed'
CONE_MODEL_EVIDENCE
echo 'CONE_SUMMARY:'
cat "$work/results.tsv"
echo 'RESULT: GATE_CONE_DIAGNOSTICS_COMPLETE (all substitutions diagnostic only; no final acceptance)'
echo "WORK_DIR: $work"
