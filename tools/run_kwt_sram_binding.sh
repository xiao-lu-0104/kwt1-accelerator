#!/usr/bin/env bash
# Foundry-model functional regression, then optional real-library synthesis.
# Creates an isolated run; never edits the competition CPU/platform/library.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
sram_root=/storage1/admin_public_dir/SRAM_Lib_2025
output_parent="${HOME}/soc"
suite=full
synthesize=0
param_handshake=0
usage() { echo "Usage: bash $0 [--suite unit|full] [--synth] [--param-handshake] [--sram-root DIR] [--output-parent DIR]"; }
while (($#)); do
    case "$1" in
        --suite|--sram-root|--output-parent)
            (($# >= 2)) || { usage; exit 2; }
            case "$1" in
                --suite) suite=$2;; --sram-root) sram_root=$2;; --output-parent) output_parent=$2;;
            esac
            shift 2;;
        --synth) synthesize=1; shift;;
        --param-handshake) param_handshake=1; shift;;
        -h|--help) usage; exit 0;;
        *) usage; exit 2;;
    esac
done
[[ "$suite" == unit || "$suite" == full ]] || { usage; exit 2; }
if ((synthesize)) && [[ "$suite" != full ]]; then
    echo 'ENV_ERROR: --synth requires --suite full'; exit 2
fi
for program in vcs timeout sha256sum cp tee; do
    command -v "$program" >/dev/null || { echo "ENV_ERROR: missing $program; load EDA environment first"; exit 2; }
done
if [[ -f "$package_root/MANIFEST.sha256" ]]; then
    (cd "$package_root"; sha256sum --quiet -c MANIFEST.sha256) || { echo 'ENV_ERROR: package checksum mismatch'; exit 2; }
fi
for name in RAMTP128X16 RAMTP1024X16; do
    [[ -f "$sram_root/$name/verilog/$name.v" ]] || { echo "ENV_ERROR: missing $name model"; exit 2; }
done
[[ -f "$package_root/rtl/kwt_sram_pins.vh" ]] || { echo 'ENV_ERROR: missing checked pin configuration'; exit 2; }
if [[ "$suite" == full ]]; then
    [[ -s "$package_root/sim/vectors/enc12/expect.mem" ]] || { echo 'ENV_ERROR: encoder vectors absent'; exit 2; }
    if ((param_handshake)); then
        [[ -s "$package_root/sim/vectors/enc12/param_stream.mem" ]] || { echo 'ENV_ERROR: packed parameter stream absent'; exit 2; }
    fi
fi
mkdir -p "$output_parent"
work=$(mktemp -d "$output_parent/kwt_sram_$(date +%Y%m%d_%H%M%S)_XXXXXX")
mkdir -p "$work/src" "$work/models" "$work/logs"
exec > >(tee "$work/runner.log") 2>&1
stage=setup
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo "SUITE: $suite; SYNTHESIS_REQUESTED: $synthesize"
echo 'BINDING_REVISION: 20261030_v10_parameter_handshake'
echo "VCS: $(command -v vcs)"
echo 'MODE: split-phase candidate; A=root rising, staged B=root falling; COLLDISN=1'
echo 'TIMING_CHECKS: enabled for 150MHz phase test; disabled for ideal RTL adapter/packed/encoder tests'
echo 'QUALIFICATION: internal collision logic remains enabled; ideal functional tests alone do not prove collision timing'
echo 'MACRO_PORT_MODE: default logical interface (no explicit VDDCE/VDDPE/VSSE ports)'
echo 'EXPECTED: 40 physical RAMTP1024X16 cells / 80 KiB; 3159181 unstalled encoder cycles (FFN length fix)'
mkdir -p "$work/src/rtl" "$work/src/tb" "$work/src/syn"
cp "$package_root/rtl/"*.v "$package_root/rtl/"*.vh "$work/src/rtl/"
cp "$package_root/tb/tb_kwt_foundry_sram16.v" "$package_root/tb/tb_kwt_packed_sram.v" \
   "$package_root/tb/tb_kwt_encoder_12.v" "$package_root/tb/tb_kwt_sram_phase.v" "$work/src/tb/"
if ((param_handshake)); then
    cp "$package_root/tb/tb_kwt_param_stream.v" "$package_root/tb/tb_kwt_encoder_param_load.v" "$work/src/tb/"
fi
cp "$package_root/syn/compile_kwt_sram_libs.tcl" "$package_root/syn/dc_compact.tcl" "$package_root/syn/kwt_encoder_12.sdc" "$work/src/syn/"
if [[ "$suite" == full ]]; then
    mkdir -p "$work/vectors"
    cp -R "$package_root/sim/vectors/enc12" "$work/vectors/"
fi
models=()
includes=("+incdir+$work/src/rtl")
for name in RAMTP128X16 RAMTP1024X16; do
    mkdir -p "$work/models/$name"
    cp -R "$sram_root/$name/verilog/." "$work/models/$name/"
    models+=("$work/models/$name/$name.v")
    includes+=("+incdir+$work/models/$name")
done
find "$work/src" "$work/models" -type f -print0 | sort -z | xargs -0 sha256sum > "$work/source_sha256.txt"
if [[ "$suite" == full ]]; then
    find "$work/vectors" -type f -print0 | sort -z | xargs -0 sha256sum > "$work/vector_sha256.txt"
fi
printf 'stage\tresult\n' > "$work/results.tsv"
common=(-full64 -sverilog -timescale=1ns/1ps
        +define+KWT_ASIC_SRAM "${includes[@]}")
# The supplied Verilog declares alternative module interfaces conditionally.
# VCS's default branch (confirmed by UPIM-E diagnostics) omits power ports.
# Do not define KWT_SRAM_POWER_PINS without also selecting the matching vendor
# power-aware model branch. Raw-text inventory alone cannot establish that.

show_compile_error() {
    local log=$1
    echo "COMPILE_LOG: $log"
    echo 'FIRST_COMPILER_DIAGNOSTIC:'
    # A tail-only display hid the useful first diagnostic behind the maximum
    # error count message. Show the first error and nearby context compactly.
    awk '
        /Error-|Error:|Fatal:|error:|syntax error/ && !started {started=1}
        started {print; count++; if (count >= 18) exit}
        END {if (!started) exit 1}
    ' "$log" || head -n 20 "$log"
}

run_test() {
    local top=$1 marker=$2
    shift 2
    local directory="$work/$top"
    local compile_log="$work/logs/${top}_compile.log"
    local sim_log="$work/logs/${top}_sim.log"
    # Bash 4.2 + nounset rejects expansion of an explicitly empty array.
    # Keep one nonempty argv array for both the recorded and executed command.
    local compile_command=(timeout 900 vcs "${common[@]}")
    if [[ "$top" == tb_kwt_sram_phase ]]; then
        echo 'PHASE_TEST: specify checks ON; period 6.667 ns, spacing 3.333/3.334 ns; default vendor collision window retained'
    else
        compile_command+=(+notimingcheck)
    fi
    compile_command+=("${models[@]}" "$@" -top "$top" -o simv)
    stage="compile_$top"
    mkdir -p "$directory"
    echo "RUN: $top (actual foundry model)"
    {
        printf '#!/usr/bin/env bash\ncd %q\n' "$directory"
        printf '%q ' "${compile_command[@]}"
        printf '\n'
    } > "$directory/compile_command.sh"
    # Separate compile/run processes and pipefail prevent tee/$finish exit=0
    # from being mistaken for a successful test.
    if ! (cd "$directory"; "${compile_command[@]}") > "$compile_log" 2>&1; then
        show_compile_error "$compile_log"; return 1
    fi
    [[ -x "$directory/simv" ]] || { show_compile_error "$compile_log"; echo 'FAIL: compiler produced no executable'; return 1; }
    stage="simulate_$top"
    if ! (cd "$work"; timeout 3600 "$directory/simv") > "$sim_log" 2>&1; then
        tail -n 60 "$sim_log"; return 1
    fi
    if ! grep -Fq "$marker" "$sim_log" || grep -Eq '(^FAIL:|MISMATCH|Fatal:|Error-\[|\$fatal|Segmentation fault|cannot be opened|unable to open|Set Value for EMA)' "$sim_log"; then
        tail -n 65 "$sim_log"; echo "FAIL: missing PASS marker or fatal diagnostic for $top"; return 1
    fi
    if [[ "$top" == tb_kwt_sram_phase ]] && grep -Eiq 'timing violation|timing check.*(fail|violat)|\$(setuphold|setup|hold|recovery|removal|width|period)[[:space:]]*\(|contention|collision.*(fail|violat)' "$sim_log"; then
        tail -n 65 "$sim_log"; echo 'FAIL: macro timing/collision diagnostic in phase test'; return 1
    fi
    if [[ "$top" == tb_kwt_encoder_12 ]] && ! grep -Eq '^cycles=3159181 outputs=6336 ' "$sim_log"; then
        tail -n 25 "$sim_log"; echo 'FAIL: encoder output count/cycles changed'; return 1
    fi
    if [[ "$top" == tb_kwt_encoder_12_stall ]] && ! grep -Eq '^PARAM_TRANSFER accepted=45384 stalls=[1-9][0-9]* ' "$sim_log"; then
        tail -n 25 "$sim_log"; echo 'FAIL: stalled encoder did not exercise parameter backpressure'; return 1
    fi
    if [[ "$top" == tb_kwt_encoder_12_stall ]] && ! grep -q '^PARAM_SERIAL_WORDS accepted=90768$' "$sim_log"; then
        tail -n 25 "$sim_log"; echo 'FAIL: stalled encoder did not consume the complete 32-bit parameter stream'; return 1
    fi
    grep -E '^(PASS:|cycles=|PROFILE encoder_|PARAM_TRANSFER|PARAM_SERIAL_WORDS)' "$sim_log"
    printf '%s\tPASS\n' "$top" >> "$work/results.tsv"
}
memory_sources=("$work/src/rtl/kwt_foundry_sram16.v" "$work/src/rtl/kwt_mem16.v")
run_test tb_kwt_sram_phase 'PASS: split-phase SRAM contract at 150MHz' \
    "${memory_sources[@]}" "$work/src/tb/tb_kwt_sram_phase.v"
run_test tb_kwt_foundry_sram16 'PASS: all foundry adapter shapes' \
    "${memory_sources[@]}" "$work/src/tb/tb_kwt_foundry_sram16.v"
run_test tb_kwt_packed_sram 'PASS: all SRAM shapes' \
    "${memory_sources[@]}" "$work/src/tb/tb_kwt_packed_sram.v"
if ((param_handshake)); then
    run_test tb_kwt_param_stream 'PASS: parameter stream 256 records' \
        "$work/src/rtl/kwt_param_stream.v" "$work/src/tb/tb_kwt_param_stream.v"
    run_test tb_kwt_encoder_param_load 'PASS: encoder parameter loading contract' \
        "$work/src/rtl/"*.v "$work/src/tb/tb_kwt_encoder_param_load.v"
fi
if [[ "$suite" == full ]]; then
    run_test tb_kwt_encoder_12 'PASS: 12-layer encoder 6336 values bit-exact' \
        "$work/src/rtl/"*.v "$work/src/tb/tb_kwt_encoder_12.v"
    if ((param_handshake)); then
        run_test tb_kwt_encoder_12_stall 'PASS: 12-layer encoder 6336 values bit-exact' \
            "$work/src/rtl/"*.v "$work/src/tb/tb_kwt_encoder_12.v"
    fi
fi
echo "FUNCTIONAL_RESULT: PASS ($suite; fresh split-phase RTL; actual foundry Verilog, not timing signoff)"

if ((synthesize)); then
    stage=library_conversion
    command -v dc_shell >/dev/null || { echo 'ENV_ERROR: dc_shell not in PATH'; exit 2; }
    if command -v lc_shell >/dev/null; then
        library_tool=lc_shell
    else
        library_tool=dc_shell
        echo 'LIBRARY_TOOL: dc_shell fallback; read_lib/write_lib require a Library Compiler license'
    fi
    export KWT_SRAM_DIR="$sram_root"
    export KWT_SRAM_DB_DIR="$work/sram_db"
    export KWT_SRAM_CONFIG_DIR="$work/src/rtl"
    export KWT_DC_REPORT_DIR="$work/dc_out_bound"
    export KWT_DC_EXPECT_SPLIT_PHASE=1
    mkdir -p "$work/sram_db"
    if ! (cd "$work"; timeout 1200 "$library_tool" -f "$work/src/syn/compile_kwt_sram_libs.tcl") > "$work/logs/library_compile.log" 2>&1; then
        tail -n 60 "$work/logs/library_compile.log"; exit 1
    fi
    grep -q '^KWT_SRAM_DB_COMPLETE$' "$work/logs/library_compile.log" || { tail -n 60 "$work/logs/library_compile.log"; exit 1; }
    for name in RAMTP128X16 RAMTP1024X16; do
        [[ -s "$work/sram_db/${name}_tt_1p10v_1p10v_25c.db" ]] || { echo "FAIL: no fresh DB for $name"; exit 1; }
        sha256sum "$sram_root/$name/lib/${name}_tt_1p10v_1p10v_25c.lib"
    done > "$work/liberty_sha256.txt"
    printf 'library_conversion\tPASS\n' >> "$work/results.tsv"
    stage=synthesis
    echo "RUN: fresh real-library synthesis; 30-minute limit; no global hold repair; log $work/logs/dc.log"
    # A fresh phase change must not inherit any old checkpoint or pilot budget.
    if ! (cd "$work"; unset KWT_RTL_ROOT KWT_DC_CHECKPOINT KWT_DC_FIX_HOLD KWT_DC_PILOT_HOLD_NS; timeout 1800 dc_shell -f "$work/src/syn/dc_compact.tcl") > "$work/logs/dc.log" 2>&1; then
        tail -n 70 "$work/logs/dc.log"; exit 1
    fi
    grep -q '^KWT_DC_COMPLETE$' "$work/logs/dc.log" || { tail -n 70 "$work/logs/dc.log"; exit 1; }
    grep -E '^(SRAM_CELLS:|SRAM_LIBRARY_AREA:|TOTAL_CELL_AREA_INCLUDING_SRAM:|AREA_LIMIT_STATUS:|SETUP_WNS:|SETUP_STATUS:|HOLD_WNS:|HOLD_STATUS:|PHASE_.*:|REPORTS:)' "$work/logs/dc.log"
    printf 'synthesis_execution\tPASS\n' >> "$work/results.tsv"
    echo 'SYNTHESIS_RESULT: COMPLETE (inspect setup/hold violations; execution success is not timing closure)'
fi
stage=complete
echo "RESULT: COMPLETE ($suite functional PASS; requested tools completed; inspect timing/area status separately)"
echo "WORK_DIR: $work"
echo "RESULTS: $work/results.tsv"
