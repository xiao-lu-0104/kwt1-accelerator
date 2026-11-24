#!/usr/bin/env bash
set -euo pipefail
work=$(realpath "$1")
case "$work" in "$HOME"/soc/tpusoc_frontend_20261110_707cd7f_*) ;; *) echo 'ERROR: unexpected run directory'; exit 2;; esac
cd "$work"
# mkdir is the single-run guard; never overwrite a previous attempt or checkpoint.
mkdir dc_attempt
exec > >(tee "$work/dc_attempt/runner.log") 2>&1
stage=preflight
trap 'rc=$?; echo "RUN_EXIT: $rc STAGE: $stage"; echo "WORK_DIR: $work"' EXIT
mkdir logs mapped sram_db
sha256sum --quiet -c MANIFEST.sha256
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/Probe.py "$work" > dc_attempt/ServerProbe.before.json.log
export TPU_STDCELL_DB=${TPU_STDCELL_DB:-/storage1/2026contest/server1/s1_12usr/lib/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db}
export TPU_SRAM_ROOT=${SRAM_LIBRARY_ROOT:-/storage1/admin_public_dir/SRAM_Lib_2025}
export TPU_SHARED_SOURCE="$work/source" TPU_SHARED_TOOLS="$work/tools" TPU_ASIC_OUT="$work/mapped"
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell
[[ -x "$dc_bin" && -s "$TPU_STDCELL_DB" ]] || { echo 'ERROR: missing DC or standard-cell DB'; exit 2; }
echo "DC_BIN: $dc_bin"
echo 'SOURCE_COMMIT: 707cd7f4a0a4d416d11bac71112980079e0a9d34'
echo 'SCOPE: new accelerator/NICE/ICB/private112KiB; CPU/shared excluded'
python3 tools/VerifyMacro.py "$TPU_SRAM_ROOT" vendor_inputs.json
# Select only an actual fingerprint-checked previous private DB. No old design is read.
reuse=$(python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('ServerProbe.json').read_text())['private_db_candidates']
if len(set(x['sha256'] for x in d)) > 1:
    raise ValueError('Conflicting historical private DB fingerprints; inspect before use')
if d: print(d[0]['path'])
PY
)
if [[ -n "$reuse" ]]; then
    export TPU_SRAM_DB="$work/sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db"
    cp -- "$reuse" "$TPU_SRAM_DB"
    cmp -- "$reuse" "$TPU_SRAM_DB"
    echo "LIBRARY_REUSED: $reuse (fingerprint/vendor/source ledger checked)"
    printf '%s\n' "$reuse" > ReusedPrivateDb.txt
else
    export TPU_SRAM_DB="$work/sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db"
    stage=library
    lc_bin=${LC_BIN:-$(command -v lc_shell || true)}
    [[ -n "$lc_bin" ]] || lc_bin=$dc_bin
    python3 tools/StageWatch.py --label library --limit 600 --log "$work/logs/library.log" --cwd "$work" -- "$lc_bin" -f "$work/tools/CompileSpLib.tcl"
    grep -q '^SP_LIBRARY_COMPLETE:' logs/library.log
    if grep -Eq '^(Error:|ASIC_ERROR:)' logs/library.log; then exit 1; fi
fi
sha256sum "$TPU_STDCELL_DB" "$TPU_SRAM_DB" > library_sha256.txt
stage=dc
python3 tools/StageWatch.py --label accelerator_707cd7f_dc --limit 2400 --log "$work/logs/dc.log" --cwd "$work/mapped" -- "$dc_bin" -f "$work/tools/Run.tcl"
grep -q '^SHARED_ASIC_REPORTS_COMPLETE:' logs/dc.log
if grep -Eq '^(Error:|SHARED_ASIC_ERROR:)' logs/dc.log; then exit 1; fi
for file in baseline.ddc baseline.v baseline.sdc candidate.ddc candidate.v candidate.sdc guidance.svf summary.txt candidate_leaves.tsv outside_before.tsv outside_after.tsv; do
    [[ -s "mapped/$file" ]]
done
sha256sum mapped/{baseline,candidate}.{ddc,v,sdc} mapped/guidance.svf > mapped_sha256.txt
sha256sum --quiet -c MANIFEST.sha256
sha256sum --quiet -c library_sha256.txt
cat mapped/summary.txt
for report in check_design check_timing; do tail -n 25 "mapped/$report.rpt"; done
stage=archive
tar -czf DcReports.tar.gz SourceProvenance.json MANIFEST.sha256 library_sha256.txt mapped_sha256.txt vendor_inputs.json ServerProbe.json dc_attempt logs mapped source tools
echo 'RESULT: NEW_707CD7F_ACCELERATOR_DC_REPORTS_COMPLETE_REVIEW_PENDING'
echo 'NEXT: review native reports and hold-change evidence before system DC; no old system candidate accepted'
stage=complete
