#!/usr/bin/env bash
# Reuse a run's proven RTL/models/vectors and compiled SRAM DBs. Do not rerun
# VCS, convert libraries, modify the failed run, or alter the CPU platform.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
run_dir=''
fix_hold=0
audit_hold=0
audit_clocks=0
pilot_hold_ns=''
phase_pilot=0
usage() { echo "Usage: bash $0 --run-dir PREVIOUS_KWT_SRAM_RUN [--fix-hold | --audit-hold | --audit-sram-clocks | --pilot-hold HOLD_UNCERTAINTY_NS | --phase-pilot HOLD_UNCERTAINTY_NS]"; }
while (($#)); do
    case "$1" in
        --run-dir) (($# >= 2)) || { usage; exit 2; }; run_dir=$2; shift 2;;
        --fix-hold) fix_hold=1; shift;;
        --audit-hold) audit_hold=1; shift;;
        --audit-sram-clocks) audit_hold=1; audit_clocks=1; shift;;
        --pilot-hold) (($# >= 2)) && [[ -n "$2" ]] || { usage; exit 2; }; pilot_hold_ns=$2; fix_hold=1; shift 2;;
        --phase-pilot) (($# >= 2)) && [[ -n "$2" ]] || { usage; exit 2; }; pilot_hold_ns=$2; fix_hold=1; phase_pilot=1; shift 2;;
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
if ((phase_pilot)); then
    # Reject a coedge run even if its three old functional tests passed.
    awk -F '\t' '$1=="tb_kwt_sram_phase" && $2=="PASS" {found=1} END {exit !found}' "$run_dir/results.tsv" || {
        echo 'ENV_ERROR: phase pilot requires a passing specify-enabled split-phase test'; exit 2;
    }
    grep -Fq 'FUNCTIONAL_RESULT: PASS (full; fresh split-phase RTL;' "$run_dir/runner.log" || {
        echo 'ENV_ERROR: no full split-phase functional PASS record'; exit 2;
    }
    grep -q '^KWT_DC_COMPLETE$' "$run_dir/logs/dc.log" || {
        echo 'ENV_ERROR: fresh split-phase synthesis did not complete'; exit 2;
    }
    awk '/^PHASE_(CLOCK|WRITE)_(max|min)_WNS:/ {if ($2 !~ /^[+-]?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$/ || $2+0 < 0) bad=1; seen[$1]=1} END {for (key in seen) count++; exit !(count==4 && !bad)}' "$run_dir/logs/dc.log" || {
        echo 'ENV_ERROR: split-phase clock/write setup and hold were not all reported nonnegative'; exit 2;
    }
fi
for record in source_sha256.txt vector_sha256.txt liberty_sha256.txt; do
    sha256sum --quiet -c "$run_dir/$record" || { echo "ENV_ERROR: original inputs changed ($record)"; exit 2; }
done
[[ -s "$run_dir/sram_db/RAMTP1024X16_tt_1p10v_1p10v_25c.db" ]] || { echo 'ENV_ERROR: original SRAM DB absent'; exit 2; }
input_digest=$({ cat "$run_dir/source_sha256.txt" "$run_dir/vector_sha256.txt" "$run_dir/liberty_sha256.txt"; sha256sum "$run_dir/sram_db/RAMTP1024X16_tt_1p10v_1p10v_25c.db"; } | sha256sum | awk '{print $1}')
recovery_kind=synth_recovery
if ((fix_hold)); then recovery_kind=hold_repair; fi
if ((audit_hold)); then recovery_kind=hold_audit; fi
if ((audit_clocks)); then recovery_kind=hold_clock_audit; fi
if [[ -n "$pilot_hold_ns" ]]; then recovery_kind=hold_pilot; fi
recovery=$(mktemp -d "$run_dir/${recovery_kind}_$(date +%Y%m%d_%H%M%S)_XXXXXX")
exec > >(tee "$recovery/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (tool execution exit=$rc)"; echo "RECOVERY_DIR: $recovery"; fi' EXIT
echo 'RECOVERY_REVISION: 20261030_v9_phase_hold_pilot'
echo "ORIGINAL_RUN: $run_dir"
echo "RECOVERY_DIR: $recovery"
if ((phase_pilot)); then
    echo 'REUSED: four passing split-phase foundry-model regressions and existing SRAM DBs; input hashes verified'
    echo 'CONSTRAINT_PLAN: explicit trial only; original 1 ns baseline remains authoritative and unchanged'
else
    echo 'REUSED: three passing foundry-model regressions and existing SRAM DBs; input hashes verified'
fi
export KWT_RTL_ROOT="$run_dir/src"
export KWT_SRAM_DB_DIR="$run_dir/sram_db"
export KWT_SRAM_CONFIG_DIR="$run_dir/src/rtl"
export KWT_DC_REPORT_DIR="$recovery/dc_out_bound"
if ((fix_hold)); then export KWT_DC_FIX_HOLD=1; else unset KWT_DC_FIX_HOLD || true; fi
unset KWT_DC_PILOT_HOLD_NS || true
unset KWT_DC_AUDIT_SRAM_CLOCKS || true
unset KWT_DC_EXPECT_SPLIT_PHASE || true
if ((phase_pilot)); then export KWT_DC_EXPECT_SPLIT_PHASE=1; fi
if [[ -n "$pilot_hold_ns" ]]; then export KWT_DC_PILOT_HOLD_NS=$pilot_hold_ns; fi
# Prefer a checkpoint from a previous recovery of these exact verified inputs.
# v2 stopped before saving one, so its first recovery repeats synthesis only.
checkpoint="$run_dir/dc_out_bound/kwt_encoder_12_compiled.ddc"
for candidate in "$run_dir"/synth_recovery_*/dc_out_bound/kwt_encoder_12_compiled.ddc; do
    [[ -s "$candidate" ]] || continue
    provenance="$(dirname "$(dirname "$candidate")")/verified_input_digest.txt"
    if [[ -s "$provenance" && "$(cat "$provenance")" == "$input_digest" ]]; then checkpoint=$candidate; fi
done
if ((phase_pilot)); then
    # Always start this experiment from the new RTL's original compiled DDC.
    checkpoint="$run_dir/dc_out_bound/kwt_encoder_12_compiled.ddc"
fi
if ((audit_clocks)); then
    checkpoint=''
    for candidate in "$run_dir"/hold_pilot_*/dc_out_bound/kwt_encoder_12.ddc; do
        [[ -s "$candidate" ]] || continue
        pilot_dir=$(dirname "$(dirname "$candidate")")
        [[ -s "$pilot_dir/verified_input_digest.txt" && "$(cat "$pilot_dir/verified_input_digest.txt")" == "$input_digest" ]] || continue
        grep -q '^KWT_DC_COMPLETE$' "$pilot_dir/dc.log" || continue
        checkpoint=$candidate
    done
    [[ -n "$checkpoint" ]] || { echo 'ENV_ERROR: no completed, matching mapped pilot checkpoint for clock audit'; exit 2; }
    export KWT_DC_AUDIT_SRAM_CLOCKS=1
    echo 'AUDIT_SCOPE: mapped pilot netlist; no optimization, exceptions, or accepted constraint changes'
fi
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
    audit_marker=KWT_HOLD_AUDIT_COMPLETE
    if ((audit_clocks)); then
        timeout 60 python "$package_root/tools/inspect_kwt_sram_clock_arcs.py" --run-dir "$run_dir" | tee "$recovery/sram_clock_arc_evidence.txt"
        audit_marker=KWT_SRAM_CLOCK_AUDIT_COMPLETE
    fi
    echo "RUN: report-only hold audit; 15-minute time limit; live log $recovery/dc.log"
    if ! (cd "$recovery"; timeout 900 dc_shell -f "$audit_script") 2>&1 | tee "$recovery/dc.log"; then
        echo 'AUDIT_RESULT: FAILED_OR_TIMED_OUT (no optimization or accepted constraint change)'; exit 1
    fi
    grep -q "^${audit_marker}$" "$recovery/dc.log" || { echo 'AUDIT_RESULT: INCOMPLETE'; exit 1; }
    sha256sum --quiet -c "$recovery/audit_input_sha256.txt"
    if ((audit_clocks)); then
        grep -h -E '^(LIB_TIME_UNIT:|CLOCK_ARC:|RAW_MODEL_CLOCK_CHECK|MACRO_PDF:|MACRO_PDF_TEXT:|MACRO_DOC_LINE_|AUDIT_BASELINE_.*WNS:|CLOCK_AUDIT_)' "$recovery/sram_clock_arc_evidence.txt" "$recovery/dc.log" > "$recovery/summary.txt"
        echo "SUMMARY: $recovery/summary.txt"
        cat "$recovery/summary.txt"
    fi
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
    if ((phase_pilot)); then
        grep -E '^(ORIGINAL_(SETUP_WNS|HOLD_WNS|HOLD_STATUS):|PILOT_HOLD_UNCERTAINTY:|PHASE_.*_WNS:|TOTAL_CELL_AREA_INCLUDING_SRAM:|AREA_LIMIT_STATUS:|SETUP_WNS:|SETUP_STATUS:|HOLD_WNS:|HOLD_STATUS:|PILOT_HOLD_REPAIR_STATUS:|ORIGINAL_BUDGET_CLOSURE:|REPORTS:)' "$recovery/dc.log" > "$recovery/summary.txt"
        echo "SUMMARY: $recovery/summary.txt"
        cat "$recovery/summary.txt"
        awk '/^PHASE_(CLOCK|WRITE)_(max|min)_WNS:/ {if ($2 !~ /^[+-]?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$/ || $2+0 < 0) bad=1; seen[$1]=1} END {for (key in seen) count++; exit !(count==4 && !bad)}' "$recovery/dc.log" || {
            echo 'PILOT_RESULT: FAIL (missing/negative split-phase path checks)'; exit 1;
        }
    fi
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
