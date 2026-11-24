#!/usr/bin/env bash
# Read-only report recovery from the saved v5 candidate; never runs compile.
set -euo pipefail
if [[ $# != 2 || "$1" != --recovery-dir ]]; then
    echo 'Usage: bash RunHoldReport.sh --recovery-dir V5_RECOVERY_DIR'; exit 2
fi
previous=$(cd "$2" && pwd -P)
work=$(mktemp -d "$previous/report_recovery_20261102_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify_inputs
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "REPORT_DIR: $work"; fi' EXIT
# __HOLD_REPORT_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if command -v python3 >/dev/null; then py=python3; else py=python; fi
echo 'RECOVERY_REVISION: v5b_read_only_hold_candidate_report_and_cell_diff'
echo "PREVIOUS_RECOVERY: $previous"
echo "REPORT_DIR: $work"
"$py" "$tools/HoldReport.py" "$previous" "$work"
export TPU_STDCELL_DB TPU_SRAM_DB
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
export TPU_HOLD_TOOLS="$tools"
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo "ENV_ERROR: missing $dc_bin"; exit 2; }
export PATH="$(dirname "$dc_bin"):$PATH"
for mode in baseline candidate; do
    export TPU_ASIC_OUT="$work/$mode"
    if [[ "$mode" == baseline ]]; then
        export TPU_HOLD_DDC
        TPU_HOLD_DDC=$(cat "$work/BaselineDdc.txt")
        export TPU_HOLD_VIEW=BASELINE
    else
        export TPU_HOLD_DDC
        TPU_HOLD_DDC=$(cat "$work/CandidateDdc.txt")
        export TPU_HOLD_VIEW=CANDIDATE
    fi
    stage="report_$mode"
    echo "RUN: $mode read-only; no compile; log=$work/$mode.log"
    if ! (cd "$work"; timeout -k 15 600 "$dc_bin" -f "$tools/SnapshotHold.tcl") > "$work/$mode.log" 2>&1; then
        tail -n 55 "$work/$mode.log"; exit 1
    fi
    if grep -Eq '^(Error:|HOLD_REPORT_ERROR:)' "$work/$mode.log" || ! grep -q '^HOLD_SNAPSHOT_COMPLETE:' "$work/$mode.log"; then
        tail -n 55 "$work/$mode.log"; exit 1
    fi
done
stage=compare_snapshots
"$py" "$tools/HoldReport.py" --compare "$work"
echo 'KEY_PATH: candidate internal hold'
grep -m 3 -E 'Startpoint:|Endpoint:|slack' "$work/candidate/internal_hold.rpt"
stage=complete
echo 'RESULT: HOLD_REPORTS_COMPLETE (timing status and outside-change review reported separately)'
echo "REPORT_DIR: $work"
