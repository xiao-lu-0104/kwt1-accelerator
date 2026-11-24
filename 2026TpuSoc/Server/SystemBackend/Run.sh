#!/usr/bin/env bash
set -euo pipefail
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 required'; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
for bin in "$dc_bin" "$vcs_bin"; do [[ -x "$bin" ]] || { echo "ERROR: tool missing: $bin"; exit 2; }; done
export PATH="$(dirname "$dc_bin"):$(dirname "$vcs_bin"):$PATH"
work=$(mktemp -d "$HOME/soc/tpusoc_system_base_20261106_XXXXXX")
tools="$work/tools"
mkdir -p "$tools" "$work/contract" "$work/mapped" "$work/sram_db"
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'SCOPE: archive existing materials; validate physical 512KiB TCM port contract; map original CPU/internal ICB around frozen accelerator'
echo 'LIMIT: preparation/archive 8min; macro contract compile 5min/run 1min; shared library conversion 10min; system mapping+one hold attempt 40min'
echo 'ACCEPTANCE: intermediate system reports; full CPU+macro TCM function, system activity/power and final submission remain pending'
# __SYSTEM_BASE_TOOLS__
(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONPATH="$tools${PYTHONPATH:+:$PYTHONPATH}"
run_stage() {
    local label=$1 limit=$2 log=$3 cwd=$4
    shift 4
    "$py" -u "$tools/StageWatch.py" --label "$label" --limit "$limit" --log "$log" --cwd "$cwd" -- "$@"
}
if ! run_stage prepare_and_archive 480 "$work/prepare.log" "$work" "$py" -u "$tools/Prepare.py" "$work"; then
    tail -n 18 "$work/prepare.log"; exit 1
fi
grep -E '^(EXISTING_MATERIALS_ARCHIVED:|SYSTEM_PREP_COMPLETE:)' "$work/prepare.log"
model=$(cat "$work/SharedModel.txt")
original_ram=$(cat "$work/OriginalRam.txt")
stage=tcm_contract
status=FAIL
if run_stage compile_tcm_contract 300 "$work/contract/compile.log" "$work/contract" \
    "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps +define+FPGA+FPGA_SOURCE \
    +notimingcheck +delay_mode_zero -v "$model" "$original_ram" "$tools/TcmMacro.sv" \
    "$tools/TcmContract.sv" -top TcmContract -o simv; then
    if run_stage simulate_tcm_contract 60 "$work/contract/run.log" "$work/contract" "$work/contract/simv"; then
        if "$py" -c 'import sys; from pathlib import Path; from Summarize import contract_pass; sys.exit(0 if contract_pass(Path(sys.argv[1]).read_text()) else 1)' "$work/contract/run.log"; then
            status=PASS
        fi
    fi
fi
printf '%s\n' "$status" > "$work/contract/status.txt"
if [[ "$status" == PASS ]]; then grep '^PASS TCM_' "$work/contract/run.log";
else
    for log in "$work/contract/compile.log" "$work/contract/run.log"; do [[ ! -f "$log" ]] || tail -n 12 "$log"; done
fi
printf 'SKIPPED\n' > "$work/mapped/status.txt"
export TPU_SYSTEM_LIB TPU_SYSTEM_DB TPU_STDCELL_DB TPU_SRAM_DB TPU_SYSTEM_OUT TPU_SYSTEM_TOOLS
TPU_SYSTEM_LIB=$(cat "$work/SharedLib.txt")
TPU_SYSTEM_DB="$work/sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db"
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
TPU_SRAM_DB=$(cat "$work/SpDb.txt")
TPU_SYSTEM_OUT="$work/mapped"; TPU_SYSTEM_TOOLS="$tools"
if [[ "$status" == PASS ]]; then
    library_bin=${LC_BIN:-$(command -v lc_shell || true)}
    [[ -n "$library_bin" ]] || library_bin="$dc_bin"
    stage=convert_shared_library
    if run_stage convert_shared_library 600 "$work/library.log" "$work" "$library_bin" -f "$tools/CompileLib.tcl" \
        && grep -q '^SYSTEM_SHARED_LIB_COMPLETE:' "$work/library.log" \
        && ! grep -Eq '^(Error:|SYSTEM_SHARED_LIB_ERROR:)' "$work/library.log"; then
        stage=map_cpu_and_tcm
        if run_stage map_cpu_and_tcm 2400 "$work/mapped/dc.log" "$work/mapped" "$dc_bin" -f "$tools/System.tcl" \
            && grep -q '^SYSTEM_MAPPING_REPORTS_COMPLETE:' "$work/mapped/dc.log" \
            && ! grep -Eq '^(Error:|SYSTEM_MAPPING_ERROR:)' "$work/mapped/dc.log"; then
            printf 'COMPLETE\n' > "$work/mapped/status.txt"
        else printf 'FAIL\n' > "$work/mapped/status.txt"; tail -n 22 "$work/mapped/dc.log"; fi
    else printf 'LIBRARY_CONVERSION_FAILED\n' > "$work/mapped/status.txt"; tail -n 18 "$work/library.log"; fi
fi
stage=summary
PYTHONPATH="$tools${PYTHONPATH:+:$PYTHONPATH}" "$py" -u "$tools/Summarize.py" "$work"
echo 'RESULT: SYSTEM_BASE_COLLECTION_COMPLETE (inspect individual statuses; system power and complete functional acceptance pending)'
echo "WORK_DIR: $work"
