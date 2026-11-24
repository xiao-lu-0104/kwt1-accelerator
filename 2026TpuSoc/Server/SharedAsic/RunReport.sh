#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash SHARED_REPORT.sh [FAILED_SHARED_ASIC_RUN]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo 'ERROR: dc_shell not found'; exit 2; }
work=$(mktemp -d "$HOME/soc/tpusoc_shared_report_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "REPORT_DIR: $work"; fi' EXIT
echo "REPORT_DIR: $work"
echo 'MODE: saved baseline/candidate reports and cell diff; no compile, hold repair, RTL change or DB conversion'
# __SHARED_REPORT_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then
    "$py" "$tools/RecoverReport.py" --previous "$1" --out "$work" --tools-sha __PREVIOUS_TOOLS_SHA__
else
    "$py" "$tools/RecoverReport.py" --out "$work" --tools-sha __PREVIOUS_TOOLS_SHA__
fi
export TPU_STDCELL_DB TPU_SRAM_DB
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
export TPU_SHARED_TOOLS="$tools" TPU_REPORT_BASELINE="$work/baseline"
export PATH="$(dirname "$dc_bin"):$PATH"
for mode in baseline candidate; do
    export TPU_ASIC_OUT="$work/$mode" TPU_REPORT_MODE="$mode" TPU_REPORT_DDC
    TPU_REPORT_DDC=$(cat "$work/${mode}_ddc.txt")
    stage="report_$mode"
    echo "RUN: $mode; no compile; log=$work/$mode.log"
    if ! (cd "$work"; timeout -k 15 600 "$dc_bin" -f "$tools/Snapshot.tcl") > "$work/$mode.log" 2>&1; then
        tail -n 65 "$work/$mode.log"; exit 1
    fi
    if ! grep -q '^SHARED_SNAPSHOT_COMPLETE:' "$work/$mode.log" || grep -Eq '^(Error:|SHARED_SNAPSHOT_ERROR:)' "$work/$mode.log"; then
        tail -n 65 "$work/$mode.log"; exit 1
    fi
done
stage=compare
"$py" "$tools/RecoverReport.py" --out "$work" --compare
echo 'CANDIDATE_CHECK_TIMING:'
tail -n 25 "$work/candidate/check_timing.rpt"
echo 'CANDIDATE_CHECK_DESIGN:'
tail -n 25 "$work/candidate/check_design.rpt"
echo 'CHANGED_CONNECTIONS_SAMPLE (full file retained):'
head -c 6000 "$work/candidate/changed_connections.tsv"
echo
stage=complete
echo 'RESULT: SHARED_SAVED_REPORTS_COMPLETE (scope/equivalence acceptance separate; no synthesis rerun)'
echo "REPORT_DIR: $work"
