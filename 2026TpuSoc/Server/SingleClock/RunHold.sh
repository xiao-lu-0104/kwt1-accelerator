#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 || "$1" != --run-dir ]]; then
    echo 'Usage: bash RunHold.sh --run-dir SINGLE_CLOCK_V4_RUN'; exit 2
fi
original=$(cd "$2" && pwd -P)
work=$(mktemp -d "$original/sram_hold_20261102_XXXXXX")
tools="$work/tools"
mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify_inputs
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "RECOVERY_DIR: $work"; fi' EXIT
# __HOLD_TOOLS__
[[ -f "$tools/MANIFEST.sha256" ]] || { echo 'ENV_ERROR: use the generated standalone recovery script'; exit 2; }
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if command -v python3 >/dev/null; then py=python3; else py=python; fi
echo 'RECOVERY_REVISION: v5_single_clock_sram_hold_only'
echo "ORIGINAL_RUN: $original"
echo "RECOVERY_DIR: $work"
"$py" "$work/tools/VerifyHoldInputs.py" "$original" "$work"
export TPU_STDCELL_DB TPU_SRAM_DB
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
export TPU_HOLD_TOOLS="$work/tools"
export TPU_HOLD_DDC="$work/input.ddc"
export TPU_ASIC_OUT="$work/E203TpuBackend"
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo "ENV_ERROR: missing executable $dc_bin"; exit 2; }
export PATH="$(dirname "$dc_bin"):$PATH"
echo 'MODE: one hold-only incremental compile; scope Tpu/Core/Sram; CPU and other logic frozen'
echo 'BUDGET: unchanged 150MHz, setup/hold uncertainty=0.2/0.1ns; no false/min/max path changes'
echo 'LIMIT: 10 minutes total; no RTL synthesis, library conversion or compile loop'
stage=hold_repair
echo "RUN: E203TpuBackend; log=$work/dc.log"
if ! (cd "$work"; timeout -k 15 600 "$dc_bin" -f "$work/tools/RepairHold.tcl") > "$work/dc.log" 2>&1; then
    tail -n 65 "$work/dc.log"; exit 1
fi
if grep -Eq '^(Error:|HOLD_REPAIR_ERROR:)' "$work/dc.log" || ! grep -q '^HOLD_REPAIR_REPORTS_COMPLETE:' "$work/dc.log"; then
    tail -n 65 "$work/dc.log"; exit 1
fi
"$py" "$work/tools/VerifyHoldInputs.py" --recheck "$work"
cat "$TPU_ASIC_OUT/hold_result.txt"
for kind in setup hold; do
    echo "KEY_PATH: $kind"
    grep -m 3 -E 'Startpoint:|Endpoint:|slack' "$TPU_ASIC_OUT/internal_${kind}.rpt"
done
stage=complete
echo 'RESULT: HOLD_REPAIR_REPORTS_COMPLETE (inspect HOLD_REPAIR_STATUS; TT pre-layout only)'
echo "RECOVERY_DIR: $work"
