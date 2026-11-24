#!/usr/bin/env bash
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash POWER_REVIEW.sh [COMPLETED_TASK_POWER]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
work=$(mktemp -d "$HOME/soc/tpusoc_power_review_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=read_only_review exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: parse existing SAIF, netlist, coverage/conflict reports and platform memory sources; no EDA or simulation'
# __POWER_REVIEW_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then "$py" "$tools/ReviewTaskPower.py" --run "$1" --out "$work";
else "$py" "$tools/ReviewTaskPower.py" --out "$work"; fi
echo 'RESULT: POWER_ACTIVITY_REVIEW_COMPLETE (classification only; system power and final acceptance remain pending)'
echo "WORK_DIR: $work"
