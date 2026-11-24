#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash OBJECT_AUDIT.sh [COMPLETED_ACTIVITY_REVIEW]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo 'ERROR: DC missing'; exit 2; }
export PATH="$(dirname "$dc_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_activity_objects_20261106_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: inspect same DDC/SAIF object connections and activity; no compile, VCS or activity override'
echo 'LIMIT: read-only DC 8min/task; retain original candidate, libraries, SAIF and constraints'
# __OBJECT_AUDIT_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then "$py" "$tools/PrepareObjectAudit.py" --review "$1" --out "$work";
else "$py" "$tools/PrepareObjectAudit.py" --out "$work"; fi
export TPU_POWER_DDC TPU_STDCELL_DB TPU_SRAM_DB TPU_OBJECT_CASE TPU_OBJECT_SAIF
TPU_POWER_DDC=$(cat "$work/Ddc.txt")
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
for task in ff1 encoder; do
    stage="inspect_objects_$task"
    TPU_OBJECT_CASE="$work/$task"; TPU_OBJECT_SAIF=$(cat "$work/$task/Saif.txt")
    echo "RUN: $stage; log=$work/$task/dc.log"
    if ! timeout -k 10 480 "$dc_bin" -f "$tools/AuditActivityObjects.tcl" > "$work/$task/dc.log" 2>&1; then
        tail -n 65 "$work/$task/dc.log"; exit 1
    fi
    if ! grep -q '^ACTIVITY_OBJECT_AUDIT_DDC_COMPLETE:' "$work/$task/dc.log" \
        || grep -q '^ACTIVITY_OBJECT_AUDIT_ERROR:' "$work/$task/dc.log"; then
        tail -n 65 "$work/$task/dc.log"; exit 1
    fi
    grep '^ACTIVITY_OBJECT_AUDIT_DDC_COMPLETE:' "$work/$task/dc.log"
done
stage=summary
"$py" "$tools/SummarizeObjectAudit.py" "$work"
echo 'RESULT: ACTIVITY_OBJECT_AUDIT_COMPLETE (object evidence only; no X waiver or system-total claim)'
echo "WORK_DIR: $work"
