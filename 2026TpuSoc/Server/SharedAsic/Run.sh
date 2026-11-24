#!/usr/bin/env bash
# Generated standalone version embeds tools at the marker below.
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: bash SHARED_ASIC.sh [SUCCESSFUL_SHARED_RUN]'; exit 2; }
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo 'ERROR: dc_shell not found'; exit 2; }
export TPU_STDCELL_DB=${TPU_STDCELL_DB:-/storage1/2026contest/server1/s1_12usr/lib/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db}
export TPU_SRAM_ROOT=${SRAM_LIBRARY_ROOT:-/storage1/admin_public_dir/SRAM_Lib_2025}
[[ -s "$TPU_STDCELL_DB" ]] || { echo "ERROR: missing standard-cell DB $TPU_STDCELL_DB"; exit 2; }
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_shared_asic_20261105_XXXXXX")
tools="$work/tools"
mkdir -p "$tools" "$work/logs" "$work/sram_db"
exec > >(tee "$work/runner.log") 2>&1
stage=verify
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'SCOPE: same tested NICE+TPU+DMA+ICB+112KiB private SRAM; CPU/platform SRAM excluded'
echo 'TARGET: SMIC40 TT 150MHz, engineering IO/clock budgets; one SRAM-only hold attempt'
echo 'LIMIT: library conversion 10min, synthesis+one hold attempt 40min; no netlist simulation/power yet'
# __SHARED_ASIC_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
if [[ $# == 1 ]]; then
    "$py" "$tools/Verify.py" --run "$1" --out "$work/source" --manifest-sha __SHARED_MANIFEST_SHA__
else
    "$py" "$tools/Verify.py" --out "$work/source" --manifest-sha __SHARED_MANIFEST_SHA__
fi
"$py" "$tools/VerifyMacro.py" "$TPU_SRAM_ROOT" "$work/vendor_inputs.json"
sha256sum "$TPU_STDCELL_DB" > "$work/library_sha256.txt"
export TPU_SRAM_DB="$work/sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db"
export TPU_SHARED_TOOLS="$tools" TPU_SHARED_SOURCE="$work/source" TPU_ASIC_OUT="$work/mapped"
export PATH="$(dirname "$dc_bin"):$PATH"
library_bin=${LC_BIN:-$(command -v lc_shell || true)}
[[ -n "$library_bin" ]] || library_bin="$dc_bin"
stage=library_conversion
echo "RUN: library conversion; log=$work/logs/library.log"
if ! (cd "$work"; timeout -k 10 600 "$library_bin" -f "$tools/CompileSpLib.tcl") > "$work/logs/library.log" 2>&1; then
    tail -n 55 "$work/logs/library.log"; exit 1
fi
if ! grep -q '^SP_LIBRARY_COMPLETE:' "$work/logs/library.log" || grep -Eq '^(Error:|ASIC_ERROR:)' "$work/logs/library.log"; then
    tail -n 55 "$work/logs/library.log"; exit 1
fi
sha256sum "$TPU_SRAM_DB" >> "$work/library_sha256.txt"
stage=synthesis_and_hold
echo "RUN: fresh synthesis + bounded hold repair; log=$work/logs/dc.log"
if ! (cd "$work"; timeout -k 30 2400 "$dc_bin" -f "$tools/Run.tcl") > "$work/logs/dc.log" 2>&1; then
    tail -n 65 "$work/logs/dc.log"; exit 1
fi
if ! grep -q '^SHARED_ASIC_REPORTS_COMPLETE:' "$work/logs/dc.log" || grep -Eq '^(Error:|SHARED_ASIC_ERROR:)' "$work/logs/dc.log"; then
    tail -n 65 "$work/logs/dc.log"; exit 1
fi
cat "$work/mapped/summary.txt"
for report in check_design check_timing; do
    echo "REVIEW_REPORT: $report"
    tail -n 20 "$work/mapped/$report.rpt"
done
sha256sum "$work/mapped/"{baseline,candidate}.{ddc,v,sdc} > "$work/mapped_sha256.txt"
stage=complete
echo 'RESULT: SHARED_ASIC_REPORTS_COMPLETE (tool run only; inspect timing statuses/check reports; power/netlist sim pending)'
echo "WORK_DIR: $work"
