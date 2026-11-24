#!/usr/bin/env bash
# Fresh competition-platform snapshot, actual RV32 C program, no original edits.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
platform="${HOME}/soc/e203_hbirdv2-master"
sram_root=/storage1/admin_public_dir/SRAM_Lib_2025
output_parent="${HOME}/soc"
suite=full
usage() { echo "Usage: bash $0 [--suite smoke|full] [--platform DIR] [--sram-root DIR] [--output-parent DIR]"; }
while (($#)); do
    (($#>=2)) || { usage;exit 2; }
    case "$1" in
        --suite) suite=$2;; --platform) platform=$2;;
        --sram-root) sram_root=$2;; --output-parent) output_parent=$2;;
        *) usage;exit 2;;
    esac
    shift 2
done
[[ "$suite" == smoke || "$suite" == full ]] || { usage;exit 2; }
for program in vcs timeout sha256sum cp tee find sort cmp; do
    command -v "$program" >/dev/null || { echo "ENV_ERROR: missing $program";exit 2; }
done
python_tool=''
for candidate in python3 python;do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys' >/dev/null 2>&1;then python_tool=$candidate;break;fi
done
[[ -n "$python_tool" ]] || { echo 'ENV_ERROR: Python 2.7 or Python 3 required for checked peripheral replacement';exit 2; }
if [[ -f "$package_root/MANIFEST.sha256" ]]; then
    (cd "$package_root";sha256sum --quiet -c MANIFEST.sha256) || { echo 'ENV_ERROR: package checksum mismatch';exit 2; }
fi
if [[ -f "$platform/vsim/install/rtl/core/config.v" ]]; then
    source_rtl="$platform/vsim/install/rtl"
else source_rtl="$platform/rtl/e203";fi
[[ -f "$source_rtl/subsys/e203_subsys_mems.v" ]] || { echo 'ENV_ERROR: platform source missing';exit 2; }
for name in RAMTP128X16 RAMTP1024X16;do
    [[ -f "$sram_root/$name/verilog/$name.v" ]] || { echo "ENV_ERROR: missing $name model";exit 2; }
done
for kind in smoke full;do
    for file in itcm.mem dtcm.mem program.elf build.json kwt_e203_images.vh;do
        [[ -s "$package_root/images/$kind/$file" ]] || { echo "ENV_ERROR: missing images/$kind/$file";exit 2; }
    done
done
cmp "$package_root/images/smoke/kwt_e203_images.vh" "$package_root/images/full/kwt_e203_images.vh" || { echo 'ENV_ERROR: image layouts differ';exit 2; }
mkdir -p "$output_parent"
work=$(mktemp -d "$output_parent/kwt_e203_$(date +%Y%m%d_%H%M%S)_XXXXXX")
exec > >(tee "$work/runner.log") 2>&1
stage=setup
trap 'rc=$?;if ((rc));then echo "RESULT: FAIL (stage=$stage exit=$rc)";echo "WORK_DIR: $work";fi' EXIT
echo "WORK_DIR: $work"
echo 'REVISION: 20261030_v12_e203_c_driver'
echo "PLATFORM_SOURCE: $source_rtl"
echo "SUITE: $suite; CPU_PROGRAM: prebuilt RV32 C application + kwt_encoder.c; source/build hashes included"
echo 'MODE: real CPU and ICB-AXI bridge; platform TCM behavioral memories; accelerator foundry models'
echo 'BOUNDARY: competition e203_soc_top with original boot/reset path; external clock/reset pads driven by testbench'
echo 'TIMING_SCOPE: functional, no SDF, +notimingcheck; no synthesis or timing signoff'
echo 'MODEL_SOURCE: full parameters/input preloaded into existing 256 KiB ITCM + 256 KiB DTCM'
mkdir -p "$work/platform" "$work/rtl" "$work/tb" "$work/models" "$work/logs" "$work/vectors"
cp -a "$source_rtl/." "$work/platform/"
touch "$work/platform/.kwt_isolated_snapshot"
find "$work/platform" -type f -print0 |sort -z|xargs -0 sha256sum > "$work/platform_before.sha256"
stage=platform_preparation
"$python_tool" "$package_root/tools/prepare_e203_kwt.py" --rtl "$work/platform" --record "$work/platform_patch.json"
cp "$package_root/rtl/"*.v "$package_root/rtl/"*.vh "$work/rtl/"
cp "$package_root/tb/tb_kwt_e203.v" "$work/tb/"
cp -R "$package_root/images" "$work/"
cp -R "$package_root/sim/vectors/enc12" "$work/vectors/"
models=()
includes=("+incdir+$work/platform/core" "+incdir+$work/platform/perips" "+incdir+$work/platform/perips/apb_i2c"
          "+incdir+$work/rtl" "+incdir+$work/images/full")
for name in RAMTP128X16 RAMTP1024X16;do
    mkdir -p "$work/models/$name"
    cp -R "$sram_root/$name/verilog/." "$work/models/$name/"
    models+=("$work/models/$name/$name.v")
    includes+=("+incdir+$work/models/$name")
done
sources=()
while IFS= read -r -d '' source_file;do sources+=("$source_file");done < <(find "$work/platform" -mindepth 2 -maxdepth 3 -type f -name '*.v' -print0|sort -z)
sources+=("$work/rtl/"*.v "$work/tb/tb_kwt_e203.v")
find "$work/platform" "$work/rtl" "$work/tb" "$work/models" "$work/images" -type f -print0|sort -z|xargs -0 sha256sum > "$work/run_inputs.sha256"
compile_command=(timeout -k 15s 900 vcs -full64 -sverilog -timescale=1ns/1ps +define+FPGA +define+KWT_ASIC_SRAM
                 +notimingcheck "${includes[@]}" "${models[@]}" "${sources[@]}" -top tb_kwt_e203 -o "$work/simv")
{ printf '#!/usr/bin/env bash\n';printf '%q ' "${compile_command[@]}";printf '\n'; } > "$work/compile_command.sh"
stage=compile
echo "RUN: fresh E203 + encoder compile; 15-minute limit; log $work/logs/compile.log"
if ! (cd "$work";"${compile_command[@]}") > "$work/logs/compile.log" 2>&1;then
    awk '/Error-|Error:|Fatal:|error:/{started=1} started{print;n++;if(n==24)exit}' "$work/logs/compile.log"
    tail -n 12 "$work/logs/compile.log";exit 1
fi
[[ -x "$work/simv" ]] || { echo 'FAIL: no fresh simulator';exit 1; }
if grep -Eq 'Error-\[|^Error:|^Fatal:' "$work/logs/compile.log";then
    tail -n 35 "$work/logs/compile.log";echo 'FAIL: compiler diagnostic despite successful exit';exit 1
fi
printf 'stage\tresult\n' > "$work/results.tsv"
run_case() {
    local kind=$1 marker=$2 smoke_flag=$3
    stage="simulate_$kind"
    echo "RUN: E203 C program $kind; 20-minute wall limit; log $work/logs/$kind.log"
    if ! (cd "$work";timeout -k 15s 1200 ./simv "+IMAGE_DIR=$work/images/$kind" "+VECTOR_DIR=$work/vectors/enc12" "+SMOKE=$smoke_flag") > "$work/logs/$kind.log" 2>&1;then
        tail -n 40 "$work/logs/$kind.log";return 1
    fi
    if ! grep -Fq "$marker" "$work/logs/$kind.log" || grep -Eiq '(^FAIL:|MISMATCH|Fatal:|(^|[[:space:]])Error:|Error-\[|\$fatal|cannot be opened|unable to open|Segmentation fault|Time Out)' "$work/logs/$kind.log";then
        tail -n 40 "$work/logs/$kind.log";echo "FAIL: missing $kind PASS or runtime diagnostic";return 1
    fi
    if [[ "$kind" == full ]] && ! grep -Eq '^CPU_TASK inputs=1584 parameter_words=90768 output_words=1584 core_cycles=[1-9][0-9]* peripheral_cycles=[1-9][0-9]* cpu_cycles=[1-9][0-9]* instructions=[1-9][0-9]*$' "$work/logs/$kind.log";then
        tail -n 20 "$work/logs/$kind.log";echo 'FAIL: missing complete CPU task measurements';return 1
    fi
    grep -E '^(CPU_|PASS:)' "$work/logs/$kind.log"
    printf '%s\tPASS\n' "$kind" >> "$work/results.tsv"
}
run_case smoke 'PASS: E203 CPU boot / C program / ICB-AXI MMIO / input / reset' 1
if [[ "$suite" == full ]];then
    run_case full 'PASS: E203 CPU C driver full encoder / 6336 shared-memory bytes bit-exact' 0
fi
stage=complete
echo "RESULT: PASS ($suite; actual CPU instruction execution, not timing signoff)"
echo "RESULTS: $work/results.tsv"
echo "WORK_DIR: $work"
