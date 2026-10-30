#!/usr/bin/env bash
# Reuse a run's proven RTL/models/vectors and compiled SRAM DBs. Do not rerun
# VCS, convert libraries, modify the failed run, or alter the CPU platform.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
run_dir=''
fix_hold=0
audit_hold=0
pilot_hold_ns=''
usage() { echo "Usage: bash $0 --run-dir PREVIOUS_KWT_SRAM_RUN [--fix-hold | --audit-hold | --pilot-hold HOLD_UNCERTAINTY_NS]"; }
while (($#)); do
    case "$1" in
        --run-dir) (($# >= 2)) || { usage; exit 2; }; run_dir=$2; shift 2;;
        --fix-hold) fix_hold=1; shift;;
        --audit-hold) audit_hold=1; shift;;
        --pilot-hold) (($# >= 2)) && [[ -n "$2" ]] || { usage; exit 2; }; pilot_hold_ns=$2; fix_hold=1; shift 2;;
        -h|--help) usage; exit 0;;
        *) usage; exit 2;;
    esac
done
[[ -n "$run_dir" ]] || { usage; exit 2; }
((fix_hold && audit_hold)) && { usage; exit 2; }
run_dir=$(cd "$run_dir" && pwd -P)
for program in dc_shell timeout sha256sum awk; do
    command -v "$program" >/dev/null || { echo "ENV_ERROR: missing $program"; exit 2; }
done
if [[ -n "$pilot_hold_ns" ]]; then
    [[ "$pilot_hold_ns" =~ ^[0-9]+([.][0-9]+)?$ ]] && awk -v n="$pilot_hold_ns" 'BEGIN {exit !(n >= 0 && n < 1)}' || {
        echo 'ENV_ERROR: pilot hold uncertainty must be a numeric value >= 0 and < 1 ns'; exit 2;
    }
fi
if [[ -f "$package_root/MANIFEST.sha256" ]]; then
    (cd "$package_root"; sha256sum --quiet -c MANIFEST.sha256) || { echo 'ENV_ERROR: fix-package checksum mismatch'; exit 2; }
fi
[[ -s "$run_dir/results.tsv" && -s "$run_dir/source_sha256.txt" && -s "$run_dir/vector_sha256.txt" && -s "$run_dir/liberty_sha256.txt" ]] || {
    echo 'ENV_ERROR: original run is missing validation records'; exit 2;
}
for completed in tb_kwt_foundry_sram16 tb_kwt_packed_sram tb_kwt_encoder_12 library_conversion; do
    awk -F '\t' -v expected="$completed" '$1==expected && $2=="PASS" {found=1} END {exit !found}' "$run_dir/results.tsv" || {
        echo "ENV_ERROR: $completed did not pass in the original run"; exit 2;
    }
done
for record in source_sha256.txt vector_sha256.txt liberty_sha256.txt; do
    sha256sum --quiet -c "$run_dir/$record" || { echo "ENV_ERROR: original inputs changed ($record)"; exit 2; }
done
[[ -s "$run_dir/sram_db/RAMTP1024X16_tt_1p10v_1p10v_25c.db" ]] || { echo 'ENV_ERROR: original SRAM DB absent'; exit 2; }
input_digest=$({ cat "$run_dir/source_sha256.txt" "$run_dir/vector_sha256.txt" "$run_dir/liberty_sha256.txt"; sha256sum "$run_dir/sram_db/RAMTP1024X16_tt_1p10v_1p10v_25c.db"; } | sha256sum | awk '{print $1}')
recovery_kind=synth_recovery
if ((fix_hold)); then recovery_kind=hold_repair; fi
if ((audit_hold)); then recovery_kind=hold_audit; fi
if [[ -n "$pilot_hold_ns" ]]; then recovery_kind=hold_pilot; fi
recovery=$(mktemp -d "$run_dir/${recovery_kind}_$(date +%Y%m%d_%H%M%S)_XXXXXX")
exec > >(tee "$recovery/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (tool execution exit=$rc)"; echo "RECOVERY_DIR: $recovery"; fi' EXIT
echo 'RECOVERY_REVISION: 20261030_v6_hold_pilot'
echo "ORIGINAL_RUN: $run_dir"
echo "RECOVERY_DIR: $recovery"
echo 'REUSED: three passing foundry-model regressions and existing SRAM DBs; input hashes verified'
export KWT_RTL_ROOT="$run_dir/src"
export KWT_SRAM_DB_DIR="$run_dir/sram_db"
export KWT_SRAM_CONFIG_DIR="$run_dir/src/rtl"
export KWT_DC_REPORT_DIR="$recovery/dc_out_bound"
if ((fix_hold)); then export KWT_DC_FIX_HOLD=1; else unset KWT_DC_FIX_HOLD || true; fi
unset KWT_DC_PILOT_HOLD_NS || true
if [[ -n "$pilot_hold_ns" ]]; then export KWT_DC_PILOT_HOLD_NS=$pilot_hold_ns; fi
# Prefer a checkpoint from a previous recovery of these exact verified inputs.
# v2 stopped before saving one, so its first recovery repeats synthesis only.
checkpoint="$run_dir/dc_out_bound/kwt_encoder_12_compiled.ddc"
for candidate in "$run_dir"/synth_recovery_*/dc_out_bound/kwt_encoder_12_compiled.ddc; do
    [[ -s "$candidate" ]] || continue
    provenance="$(dirname "$(dirname "$candidate")")/verified_input_digest.txt"
    if [[ -s "$provenance" && "$(cat "$provenance")" == "$input_digest" ]]; then checkpoint=$candidate; fi
done
if [[ -s "$checkpoint" ]]; then
    export KWT_DC_CHECKPOINT="$checkpoint"
    echo "MODE: use compiled checkpoint $checkpoint"
else
    unset KWT_DC_CHECKPOINT || true
    if ((fix_hold || audit_hold)); then
        echo 'ENV_ERROR: hold repair/audit requires a compiled checkpoint from the verified run'; exit 2
    fi
    echo 'MODE: synthesize original verified RTL only (no compiled checkpoint in this run)'
fi
printf '%s\n' "$input_digest" > "$recovery/verified_input_digest.txt"
if ((audit_hold)); then
    audit_script="$package_root/syn/audit_kwt_hold.tcl"
    [[ -s "$audit_script" ]] || { echo 'ENV_ERROR: hold audit script absent'; exit 2; }
    cp "$audit_script" "$recovery/audit_kwt_hold_used.tcl"
    sha256sum "$audit_script" "$checkpoint" > "$recovery/audit_input_sha256.txt"
    echo "RUN: report-only hold audit; 15-minute time limit; live log $recovery/dc.log"
    if ! (cd "$recovery"; timeout 900 dc_shell -f "$audit_script") 2>&1 | tee "$recovery/dc.log"; then
        echo 'AUDIT_RESULT: FAILED_OR_TIMED_OUT (no optimization or accepted constraint change)'; exit 1
    fi
    grep -q '^KWT_HOLD_AUDIT_COMPLETE$' "$recovery/dc.log" || { echo 'AUDIT_RESULT: INCOMPLETE'; exit 1; }
    sha256sum --quiet -c "$recovery/audit_input_sha256.txt"
    echo 'RESULT: AUDIT_COMPLETE (diagnostic only; original hold remains unresolved)'
    echo "RECOVERY_DIR: $recovery"
    exit 0
fi
cp "$package_root/syn/dc_compact.tcl" "$recovery/dc_compact_used.tcl"
sha256sum "$package_root/syn/dc_compact.tcl" > "$recovery/recovery_script_sha256.txt"
if [[ -n "$pilot_hold_ns" ]]; then
    sha256sum "$checkpoint" > "$recovery/pilot_checkpoint_sha256.txt"
    echo "RUN: hold repair PILOT; explicit trial uncertainty $pilot_hold_ns ns; 20-minute limit; live log $recovery/dc.log"
    echo 'ACCEPTANCE: pilot only; original-budget timing closure remains unestablished'
    if (cd "$recovery"; timeout -k 30 1200 dc_shell -f "$package_root/syn/dc_compact.tcl") 2>&1 | tee "$recovery/dc.log"; then
        :
    else
        dc_status=$?
        if ((dc_status == 124 || dc_status == 137)); then echo 'PILOT_RESULT: TIMEOUT (optimization incomplete)'; fi
        exit "$dc_status"
    fi
    grep -q '^KWT_DC_COMPLETE$' "$recovery/dc.log" || { echo 'PILOT_RESULT: INCOMPLETE'; exit 1; }
    sha256sum --quiet -c "$recovery/pilot_checkpoint_sha256.txt"
    grep -q '^PILOT_HOLD_REPAIR_STATUS: PASS$' "$recovery/dc.log" || { echo 'PILOT_RESULT: FAIL (inspect pilot reports)'; exit 1; }
    echo 'RESULT: PILOT_COMPLETE (trial budget only; original-budget closure not established)'
    echo "RECOVERY_DIR: $recovery"
    exit 0
fi
echo "RUN: DC; log $recovery/dc.log"
if (cd "$recovery"; timeout 14400 dc_shell -f "$package_root/syn/dc_compact.tcl") > "$recovery/dc.log" 2>&1; then
    :
else
    dc_status=$?
    if ((dc_status == 124)); then echo 'TOOL_STATUS: TIMEOUT (14400 seconds; optimization/reporting incomplete)'; fi
    tail -n 65 "$recovery/dc.log"; exit "$dc_status"
fi
grep -q '^KWT_DC_COMPLETE$' "$recovery/dc.log" || { tail -n 65 "$recovery/dc.log"; exit 1; }
grep -E '^(HOLD_BEFORE_SETUP_WNS:|HOLD_BEFORE_WNS:|HOLD_REPAIR_STATUS:|SRAM_CELLS:|SRAM_LIBRARY_AREA:|TOTAL_CELL_AREA_INCLUDING_SRAM:|AREA_LIMIT_STATUS:|SETUP_WNS:|SETUP_STATUS:|HOLD_WNS:|HOLD_STATUS:|REPORTS:)' "$recovery/dc.log"
if ((fix_hold)) && ! grep -q '^HOLD_REPAIR_STATUS: PASS$' "$recovery/dc.log"; then
    echo 'HOLD_REPAIR_RESULT: FAIL (inspect area/setup/hold and before/after reports)'; exit 1
fi
echo 'RESULT: COMPLETE (synthesis/reporting; inspect area/setup/hold status separately)'
echo "RECOVERY_DIR: $recovery"
