#!/usr/bin/env bash
# Competition CPU/TCM functional integration. No synthesis or STA in this run.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
platform=${1:-"$HOME/soc/e203_hbirdv2-master"}
[[ -f "$root/MANIFEST.sha256" ]] || { echo 'ERROR: run the prepared shared-SRAM bundle'; exit 2; }
(cd "$root"; sha256sum --quiet -c MANIFEST.sha256)
py=$(command -v python3 || true)
[[ -n "$py" ]] || { echo 'ERROR: Python 3 is required for source preparation'; exit 2; }
vcs_bin=${VCS_BIN:-$(command -v vcs || true)}
[[ -n "$vcs_bin" ]] || vcs_bin=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
[[ -x "$vcs_bin" ]] || { echo 'ERROR: VCS not found'; exit 2; }
vendor=${SRAM_LIBRARY_ROOT:-/storage1/admin_public_dir/SRAM_Lib_2025}
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_shared_20261105_XXXXXX")
exec > >(tee "$work/runner.log") 2>&1
stage=prepare
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL stage=$stage exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'SCOPE: competition CPU/LSU/TCM controllers + timed external loader + real private SRAM functional model'
echo 'LIMIT: separate from full peripheral SoC acceptance, macro timing, synthesis and power'
"$py" "$root/Server/Shared/Prepare.py" --platform "$platform" --out "$work/project"
"$py" "$root/Server/Backend/VerifyMacro.py" "$vendor" "$work/vendor_inputs.json"
cp "$root/Firmware.hex" "$work/project/Firmware.hex"
stage=compile
cd "$work/project"
if ! timeout -k 10 600 "$vcs_bin" -full64 -sverilog -timescale=1ns/1ps -assert svaext \
    +define+FPGA+FPGA_SOURCE+TPU_SRAM_MODEL +notimingcheck -f Files.f \
    "$root/Server/Backend/SpFoundry.sv" "$vendor/RAMSP1024X16/verilog/RAMSP1024X16.v" \
    -top SharedTest -o simv > "$work/compile.log" 2>&1; then
    tail -n 55 "$work/compile.log"; exit 1
fi
run_case() {
    local name=$1 kind=$2 layers=$3 vectors=$4
    stage="simulate_$name"
    if ! timeout -k 10 900 ./simv +FIRMWARE="$work/project/Firmware.hex" +VECTORS="$vectors" \
        +KIND="$kind" +LAYERS="$layers" > "$work/$name.log" 2>&1; then
        tail -n 45 "$work/$name.log"; return 1
    fi
    if ! grep -q '^PASS SHARED:' "$work/$name.log" || \
        grep -Eiq '(Error-\[|Fatal:|FATAL:|FAIL:|Assertion.*failed)' "$work/$name.log"; then
        tail -n 45 "$work/$name.log"; return 1
    fi
    grep '^PASS SHARED:' "$work/$name.log"
}
for name in normal zero extreme Layer{0..11}; do
    run_case "ff1_$name" 1 1 "$root/Vectors/Ff1_$name"
done
run_case encoder_one 0 1 "$root/Vectors"
run_case encoder_twelve 0 12 "$root/Vectors"
stage=complete
echo 'RESULT: PASS SHARED_FUNCTIONAL (17 tasks; original CPU/LSU/TCM, timed loading, vendor private SRAM; no STA)'
echo "WORK_DIR: $work"
