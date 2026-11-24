#!/usr/bin/env bash
# Real SP macro verification, then independent TPU and CPU+TPU SMIC40 TT synthesis.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
selection=both
if [[ $# -gt 0 ]]; then
    if [[ $# == 2 && "$1" == --top ]]; then selection=$2;
    else echo 'Usage: bash Run.sh [--top both|tpu|soc]'; exit 2; fi
fi
case "$selection" in both|tpu|soc) ;; *) echo 'ENV_ERROR: invalid top'; exit 2;; esac
[[ -f "$package_root/MANIFEST.sha256" ]] || { echo 'ENV_ERROR: prepared source bundle required'; exit 2; }
(cd "$package_root"; sha256sum --quiet -c MANIFEST.sha256)
export TPU_SRAM_ROOT=${SRAM_LIBRARY_ROOT:-/storage1/admin_public_dir/SRAM_Lib_2025}
export TPU_STDCELL_DB=${TPU_STDCELL_DB:-/storage1/2026contest/server1/s1_12usr/lib/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_ccs.db}
[[ -s "$TPU_STDCELL_DB" ]] || { echo "ENV_ERROR: missing standard-cell DB $TPU_STDCELL_DB"; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
for tool in "$vcs_bin" "$dc_bin"; do [[ -x "$tool" ]] || { echo "ENV_ERROR: missing executable $tool"; exit 2; }; done
export PATH="$(dirname "$vcs_bin"):$(dirname "$dc_bin"):$PATH"
if command -v python3 >/dev/null; then py=python3; else py=python; fi
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_single_$(date +%Y%m%d_%H%M%S)_XXXXXX")
mkdir -p "$work/logs" "$work/project" "$work/sram_db"
cp -R "$package_root/Rtl" "$package_root/Server" "$package_root/e203_hbirdv2" "$package_root/Sim" "$package_root/Backend" "$work/project/"
exec > >(tee "$work/runner.log") 2>&1
stage=setup
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "WORK_DIR: $work"; fi' EXIT
export TPU_ASIC_ROOT="$work/project"
export TPU_SRAM_DB="$work/sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db"
echo 'BASELINE: 88e529eff28f4ba75fc250fe2e03310e267b3af7; upstream RTL unchanged'
echo "WORK_DIR: $work"
echo "TARGET: SMIC40 TT; TPU=150 MHz; CPU+TPU=shared 150 MHz; tops=$selection"
echo 'CLOCKING: one common rising-edge Clock, direct NICE; no CDC timing exceptions'
echo 'BINDING: 56 RAMSP1024X16; EMA=2 EMAW=0 RET1N=1; active-low CEN/GWEN/WEN; default logical ports'
echo 'TIMING: engineering budget setup uncertainty=0.2ns hold=0.1ns; not official/signoff'
echo 'LIMITS: VCS compile 5min/test; library conversion 10min; DC 30min/top; no global hold repair'
printf 'stage\tresult\n' > "$work/results.tsv"
stage=reviewed_vendor_inputs
"$py" "$TPU_ASIC_ROOT/Server/Backend/VerifyMacro.py" "$TPU_SRAM_ROOT" "$work/reviewed_binding.json"
cp "$package_root/MANIFEST.sha256" "$work/package_manifest.sha256"
sha256sum "$TPU_STDCELL_DB" > "$work/library_sha256.txt"
run_vcs() {
    local top=$1 marker=$2
    shift 2
    local dir="$work/vcs_$top"
    mkdir -p "$dir"
    stage="vcs_compile_$top"
    echo "RUN: $stage; log=$work/logs/$stage.log"
    if ! (cd "$dir"; timeout -k 5 300 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps \
        -assert svaext "$@" -top "$top" -o simv) > "$work/logs/$stage.log" 2>&1; then
        tail -n 45 "$work/logs/$stage.log"; return 1
    fi
    stage="vcs_run_$top"
    if ! (cd "$dir"; timeout -k 5 120 ./simv) > "$work/logs/$stage.log" 2>&1; then
        tail -n 45 "$work/logs/$stage.log"; return 1
    fi
    if ! grep -Fq "$marker" "$work/logs/$stage.log" || \
       grep -Eiq '(Timing violation|\$setuphold|\$setup\(|\$hold\(|Error-\[|Fatal:|FATAL:|FAIL:)' "$work/logs/$stage.log"; then
        tail -n 45 "$work/logs/$stage.log"; return 1
    fi
    grep -F "$marker" "$work/logs/$stage.log"
    printf '%s\tPASS\n' "$top" >> "$work/results.tsv"
}
# Functional RTL has zero-delay launch flops; setup/hold checks belong to real
# mapped-cell STA, not this ideal RTL simulation. Preserve model path delays.
run_vcs SpBindingTest 'PASS SP_BINDING:' +define+TPU_SRAM_MODEL +notimingcheck \
    "$TPU_SRAM_ROOT/RAMSP1024X16/verilog/RAMSP1024X16.v" \
    "$TPU_ASIC_ROOT/Rtl/TpuPkg.sv" "$TPU_ASIC_ROOT/Rtl/TpuSram.sv" \
    "$TPU_ASIC_ROOT/Server/Backend/SpFoundry.sv" "$TPU_ASIC_ROOT/Server/Backend/SpBindingTest.sv"
echo 'VENDOR_BINDING_FUNCTIONAL_STATUS: PASS (actual macro model; RTL timing checks disabled; path delays retained)'
echo 'TIMING_QUALIFICATION: real standard-cell/SRAM Liberty STA follows; no SDF backannotation in the RTL test'
stage=library_conversion
library_bin=${LC_BIN:-$(command -v lc_shell || true)}
if [[ -z "$library_bin" ]]; then
    library_bin=$dc_bin
    echo 'LIBRARY_TOOL: dc_shell fallback; read_lib/write_lib require Library Compiler license'
fi
echo "RUN: library conversion; log=$work/logs/library.log"
if ! (cd "$work"; timeout -k 10 600 "$library_bin" -f "$TPU_ASIC_ROOT/Server/Backend/CompileSpLib.tcl") > "$work/logs/library.log" 2>&1; then
    tail -n 50 "$work/logs/library.log"; exit 1
fi
grep -q '^SP_LIBRARY_COMPLETE:' "$work/logs/library.log" || { tail -n 40 "$work/logs/library.log"; exit 1; }
if grep -Eq '^(Error:|ASIC_ERROR:)' "$work/logs/library.log"; then tail -n 50 "$work/logs/library.log"; exit 1; fi
printf 'library_conversion\tPASS\n' >> "$work/results.tsv"
sha256sum "$TPU_SRAM_DB" >> "$work/library_sha256.txt"
tops=()
[[ "$selection" == soc ]] || tops+=(TpuNiceAxi)
[[ "$selection" == tpu ]] || tops+=(E203TpuBackend)
for top in "${tops[@]}"; do
    export TPU_ASIC_TOP="$top"
    export TPU_ASIC_OUT="$work/$top"
    stage="synthesis_$top"
    echo "RUN: $stage; log=$work/logs/$top.log"
    if ! (cd "$work"; timeout -k 30 1800 "$dc_bin" -f "$TPU_ASIC_ROOT/Server/SingleClock/Run.tcl") > "$work/logs/$top.log" 2>&1; then
        tail -n 55 "$work/logs/$top.log"; exit 1
    fi
    grep -q '^ASIC_REPORTS_COMPLETE:' "$work/logs/$top.log" || { tail -n 55 "$work/logs/$top.log"; exit 1; }
    if grep -Eq '^(Error:|ASIC_ERROR:)' "$work/logs/$top.log"; then tail -n 55 "$work/logs/$top.log"; exit 1; fi
    cat "$TPU_ASIC_OUT/summary.txt"
    printf '%s\tREPORTS_COMPLETE\n' "$top" >> "$work/results.tsv"
done
stage=complete
echo 'RESULT: REPORTS_COMPLETE (tool execution only; inspect single-clock setup/hold statuses separately)'
echo "WORK_DIR: $work"
