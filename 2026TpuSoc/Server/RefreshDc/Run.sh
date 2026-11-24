#!/usr/bin/env bash
set -euo pipefail
work=$1
cd "$work"
exec > >(tee "$work/runner.log") 2>&1
stage=preflight
trap 'rc=$?; echo "RUN_EXIT: $rc STAGE: $stage"; echo "WORK_DIR: $work"; if ((rc)); then tail -n 45 "$work/logs/$stage.log" 2>/dev/null || true; fi' EXIT
mkdir logs mapped sram_db
sha256sum --quiet -c MANIFEST.sha256
export TPU_STDCELL_DB=${TPU_STDCELL_DB:-/storage1/2026contest/server1/s1_12usr/lib/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db}
export TPU_SRAM_ROOT=${SRAM_LIBRARY_ROOT:-/storage1/admin_public_dir/SRAM_Lib_2025}
export TPU_SRAM_DB="$work/sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db"
export TPU_SHARED_SOURCE="$work/source" TPU_SHARED_TOOLS="$work/tools" TPU_ASIC_OUT="$work/mapped"
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo "ERROR: DC executable missing: $dc_bin"; exit 2; }
[[ -s "$TPU_STDCELL_DB" ]] || { echo "ERROR: standard-cell DB missing: $TPU_STDCELL_DB"; exit 2; }
echo "DC_BIN: $dc_bin"
echo "STDCELL_DB: $TPU_STDCELL_DB"
py=$(command -v python3)
"$py" tools/VerifyMacro.py "$TPU_SRAM_ROOT" vendor_inputs.json
sha256sum "$TPU_STDCELL_DB" > library_sha256.txt
export PATH="$(dirname "$dc_bin"):$PATH"
lc_bin=${LC_BIN:-$(command -v lc_shell || true)}
[[ -n "$lc_bin" ]] || lc_bin=$dc_bin
stage=library
"$py" tools/StageWatch.py --label library --limit 600 --log "$work/logs/library.log" --cwd "$work" -- "$lc_bin" -f "$work/tools/CompileSpLib.tcl"
grep -q '^SP_LIBRARY_COMPLETE:' logs/library.log
if grep -Eq '^(Error:|ASIC_ERROR:)' logs/library.log; then exit 1; fi
sha256sum "$TPU_SRAM_DB" >> library_sha256.txt
stage=dc
echo 'SCOPE: fresh c03eb04 accelerator + existing platform ICB; TT 150MHz; no system synthesis yet'
echo 'LIMIT: DC 40min including at most one SRAM-only hold attempt; limit is not an estimate'
"$py" tools/StageWatch.py --label dc --limit 2400 --log "$work/logs/dc.log" --cwd "$work/mapped" -- "$dc_bin" -f "$work/tools/Run.tcl"
grep -q '^SHARED_ASIC_REPORTS_COMPLETE:' logs/dc.log
if grep -Eq '^(Error:|SHARED_ASIC_ERROR:)' logs/dc.log; then exit 1; fi
for file in baseline.ddc baseline.v baseline.sdc candidate.ddc candidate.v candidate.sdc guidance.svf summary.txt; do
    [[ -s "mapped/$file" ]]
done
sha256sum mapped/{baseline,candidate}.{ddc,v,sdc} mapped/guidance.svf > mapped_sha256.txt
sha256sum --quiet -c MANIFEST.sha256
sha256sum --quiet -c library_sha256.txt
cat mapped/summary.txt
for report in check_design check_timing; do
    echo "REVIEW_REPORT: $report"
    tail -n 20 "mapped/$report.rpt"
done
stage=archive
tar -czf DcReports.tar.gz SourceProvenance.json MANIFEST.sha256 library_sha256.txt mapped_sha256.txt vendor_inputs.json logs mapped source tools
echo 'RESULT: NEW_ACCELERATOR_DC_REPORTS_COMPLETE_REVIEW_PENDING'
echo 'NEXT: inspect setup/hold/check reports before E203 system synthesis; function/formal/power not qualified'
stage=complete
