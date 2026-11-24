#!/usr/bin/env bash
# G1 first step: audit actual RAMSP files and test the NEW logical controller.
# The local test double is explicit. No guessed foundry binding or synthesis.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
sram_root=/storage1/admin_public_dir/SRAM_Lib_2025
output_parent="${HOME}/soc"
audit_only=0
while (($#)); do
    case "$1" in
        --sram-root|--output-parent)
            (($#>=2)) || { echo 'ENV_ERROR: missing option value'; exit 2; }
            case "$1" in --sram-root) sram_root=$2;; --output-parent) output_parent=$2;; esac
            shift 2;;
        --audit-only) audit_only=1; shift;;
        -h|--help) echo "Usage: bash $0 [--audit-only] [--sram-root DIR] [--output-parent DIR]"; exit 0;;
        *) echo "ENV_ERROR: unknown option $1"; exit 2;;
    esac
done
for program in python timeout sha256sum tee; do
    command -v "$program" >/dev/null || { echo "ENV_ERROR: missing $program"; exit 2; }
done
if [[ -f "$package_root/MANIFEST.sha256" ]]; then
    (cd "$package_root"; sha256sum --quiet -c MANIFEST.sha256) || { echo 'ENV_ERROR: package checksum mismatch'; exit 2; }
fi
mkdir -p "$output_parent"
work=$(mktemp -d "$output_parent/kwt_sp_foundation_$(date +%Y%m%d_%H%M%S)_XXXXXX")
mkdir -p "$work/logs" "$work/src/rtl" "$work/src/tb/models" "$work/src/tools"
exec > >(tee "$work/runner.log") 2>&1
stage=setup
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "WORK_DIR: $work"; fi' EXIT
echo 'REVISION: 20261031_sp_foundation_v1'
echo "WORK_DIR: $work"
echo 'SCOPE: RAMSP evidence + logical controller test; no CPU/core change, no hold repair'
echo 'LIMITS: audit 120s; datasheets 120s; compile 120s; simulation 30s (+5s exit grace each)'
cp "$package_root/rtl/kwt_sp_sram_ctrl.v" "$work/src/rtl/"
cp "$package_root/tb/tb_kwt_sp_sram_ctrl.v" "$work/src/tb/"
cp "$package_root/tb/models/kwt_sp_memory_model.v" "$work/src/tb/models/"
for name in audit_kwt_sp_macro.py inspect_kwt_sram.py inspect_kwt_sram_clock_arcs.py read_kwt_sram_datasheets.py; do
    cp "$package_root/tools/$name" "$work/src/tools/"
done
find "$work/src" -type f -print0 | sort -z | xargs -0 sha256sum > "$work/source_sha256.txt"
stage=audit
if ! timeout -k 5 120 python "$work/src/tools/audit_kwt_sp_macro.py" --root "$sram_root" --out-dir "$work/audit" > "$work/logs/audit.log" 2>&1; then
    tail -n 20 "$work/logs/audit.log"; exit 1
fi
cat "$work/audit/summary.txt"
stage=datasheets
datasheet_status=INCOMPLETE
if timeout -k 5 120 python "$work/src/tools/read_kwt_sram_datasheets.py" --root "$sram_root" --macro RAMSP1024X16 --out-dir "$work/datasheets" > "$work/logs/datasheets.log" 2>&1; then
    datasheet_status=EXTRACTED_REVIEW_PENDING
fi
echo "DATASHEET_STATUS: $datasheet_status"
echo "DATASHEET_LOG: $work/logs/datasheets.log"
if [[ -f "$work/datasheets/summary.txt" ]]; then
    # Keep terminal excerpts bounded; full extracted text remains in the run.
    awk '/^(DATASHEET_TEXT:|DATASHEET_LINE_|EXTRACTION_UNRESOLVED:)/ {print; n++; if(n==8) exit}' "$work/datasheets/summary.txt"
else
    tail -n 6 "$work/logs/datasheets.log"
fi
protocol_status=NOT_RUN
if ((!audit_only)); then
    command -v vcs >/dev/null || { echo 'ENV_ERROR: vcs absent; use --audit-only to collect evidence'; exit 2; }
    mkdir -p "$work/protocol"
    stage=compile_protocol
    echo 'RUN: new controller protocol / explicit test double / nominal 150MHz'
    if ! (cd "$work/protocol"; timeout -k 5 120 vcs -full64 -sverilog -timescale=1ns/1ps \
        "$work/src/rtl/kwt_sp_sram_ctrl.v" "$work/src/tb/models/kwt_sp_memory_model.v" \
        "$work/src/tb/tb_kwt_sp_sram_ctrl.v" -top tb_kwt_sp_sram_ctrl -o simv) > "$work/logs/compile.log" 2>&1; then
        awk '/Error-|Error:|Fatal:|syntax error/ && !s {s=1} s {print; if(++n==18) exit}' "$work/logs/compile.log"
        echo "COMPILE_LOG: $work/logs/compile.log"; exit 1
    fi
    stage=simulate_protocol
    if ! (cd "$work/protocol"; timeout -k 5 30 ./simv) > "$work/logs/simulation.log" 2>&1; then
        tail -n 20 "$work/logs/simulation.log"; exit 1
    fi
    if ! grep -Fq 'PASS: all SP controller protocol tests' "$work/logs/simulation.log" || \
       grep -Eiq '(^FAIL|Fatal:|FATAL:|Error-|timing violation|Segmentation fault)' "$work/logs/simulation.log"; then
        tail -n 20 "$work/logs/simulation.log"; exit 1
    fi
    grep '^PASS:' "$work/logs/simulation.log"
    protocol_status=PASS_TEST_DOUBLE_ONLY
fi
stage=complete
{
    echo "PROTOCOL_STATUS: $protocol_status"
    echo "DATASHEET_STATUS: $datasheet_status"
    echo 'FOUNDRY_BINDING_STATUS: PENDING_PORT_AND_CONTROL_REVIEW'
    echo 'FOUNDRY_TIMING_STATUS: NOT_RUN'
    echo 'SYNTHESIS_STATUS: NOT_RUN'
    echo 'G1_STATUS: OPEN (protocol alone does not qualify physical SRAM)'
    echo 'RESULT: FOUNDATION_REVIEW_READY'
    echo "AUDIT_SUMMARY: $work/audit/summary.txt"
    echo "WORK_DIR: $work"
} | tee "$work/summary.txt"
