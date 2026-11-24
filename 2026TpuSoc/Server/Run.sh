#!/usr/bin/env bash
# Run this repository's original tests, without server compiler dependencies.
# Prebuilt x86-64 models are statically linked, assertion-enabled Verilator RTL.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
output_parent="${HOME}/soc"
suite=full
vcs_units=0
while (($#)); do
    case "$1" in
        --suite|--output-parent)
            (($#>=2)) || { echo 'ENV_ERROR: missing option value'; exit 2; }
            case "$1" in --suite) suite=$2;; --output-parent) output_parent=$2;; esac
            shift 2;;
        --vcs-units) vcs_units=1; shift;;
        -h|--help) echo "Usage: bash $0 [--suite smoke|full] [--vcs-units] [--output-parent DIR]"; exit 0;;
        *) echo "ENV_ERROR: unknown option $1"; exit 2;;
    esac
done
[[ "$suite" == smoke || "$suite" == full ]] || { echo 'ENV_ERROR: invalid suite'; exit 2; }
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || { echo 'ENV_ERROR: Linux x86_64 required'; exit 2; }
for tool in timeout sha256sum tee; do
    command -v "$tool" >/dev/null || { echo "ENV_ERROR: missing $tool"; exit 2; }
done
if command -v python3 >/dev/null; then python_cmd=python3; else python_cmd=python; fi
command -v "$python_cmd" >/dev/null || { echo 'ENV_ERROR: Python 2.7/3 needed for software-head check'; exit 2; }
[[ -f "$package_root/MANIFEST.sha256" ]] || { echo 'ENV_ERROR: run a prepared server bundle'; exit 2; }
(cd "$package_root"; sha256sum --quiet -c MANIFEST.sha256) || { echo 'ENV_ERROR: package hash mismatch'; exit 2; }
mkdir -p "$output_parent"
work=$(mktemp -d "$output_parent/tpusoc_$(date +%Y%m%d_%H%M%S)_XXXXXX")
mkdir -p "$work/project" "$work/logs"
cp -R "$package_root/." "$work/project/"
exec > >(tee "$work/runner.log") 2>&1
stage=setup
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "WORK_DIR: $work"; fi' EXIT
cd "$work/project"
chmod +x Server/Bin/*
export TPU_DDR_MBPS=600 TPU_DDR_LATENCY=12 TPU_DDR_REFRESH_PERIOD=1170 TPU_DDR_REFRESH_CYCLES=39
echo 'BASELINE: github.com/kkk73/2026TpuSoc a671d5da433c6ae2ac1479c5bfba2434f6631414'
echo "WORK_DIR: $work"
echo "SUITE: $suite; NATIVE_VCS_UNITS: $vcs_units"
echo 'MODELS: original RTL + assertion-enabled static Verilator executables; behavior SRAM/DDR'
echo 'SCOPE: functional reproduction; not foundry SRAM, ASIC synthesis or full competition-platform qualification'
printf 'stage\tresult\n' > "$work/results.tsv"
run() {
    local name=$1 marker=$2 limit=$3
    shift 3
    stage=$name
    echo "RUN: $name (limit ${limit}s)"
    if ! timeout -k 5 "$limit" "$@" > "$work/logs/$name.log" 2>&1; then
        tail -n 24 "$work/logs/$name.log"; echo "LOG: $work/logs/$name.log"; return 1
    fi
    if ! grep -Fq "$marker" "$work/logs/$name.log" || grep -Eq '(^FAIL:|^FATAL:|Fatal:|Error-\[|Assertion failed|Aborting)' "$work/logs/$name.log"; then
        tail -n 24 "$work/logs/$name.log"; return 1
    fi
    grep -E '^(PASS|DDR )' "$work/logs/$name.log" | tail -n 3
    printf '%s\tPASS\n' "$name" >> "$work/results.tsv"
}
run arithmetic 'PASS arithmetic:' 60 Server/Bin/VArithmeticTest
run nice 'PASS NICE:' 60 Server/Bin/VNiceTest
run axi 'PASS AXI128:' 90 Server/Bin/VTpuAxi
run gelu 'PASS GELU:' 60 Server/Bin/VTpuGelu
run encoder_normal 'PASS encoder:' 180 Server/Bin/VTpuTop workspace/Sim/out/synthetic/Program.txt
if [[ "$suite" == full ]]; then
    run encoder_zero 'PASS encoder:' 180 Server/Bin/VTpuTop workspace/Sim/out/zero/Program.txt
    run encoder_extreme 'PASS encoder:' 180 Server/Bin/VTpuTop workspace/Sim/out/extreme/Program.txt
    programs=()
    for layer in {0..11}; do
        program="workspace/Sim/out/official$layer/Program.txt"
        run "official_$layer" 'PASS encoder:' 180 Server/Bin/VTpuTop "$program"
        run "official_final_$layer" 'PASS encoder:' 180 Server/Bin/VTpuTop --final-only "workspace/Sim/out/official$layer/ProgramRun.txt"
        programs+=("$program")
    done
    run official_continuous 'PASS encoder:' 600 Server/Bin/VTpuTop "${programs[@]}"
fi
run soc_one 'PASS E203 + TPU: layers 1,' 600 Server/Bin/VE203Tpu workspace/Sw/Soc.bin workspace/Sim/out/Soc 1
if [[ "$suite" == full ]]; then
    run soc_twelve 'PASS E203 + TPU: layers 12,' 600 Server/Bin/VE203Tpu workspace/Sw/Soc.bin workspace/Sim/out/Soc 12
    run soc_final 'PASS E203 + TPU: layers 12,' 600 Server/Bin/VE203Tpu workspace/Sw/Soc.bin workspace/Sim/out/Soc 12 final
    run software_head 'PASS software head:' 30 "$python_cmd" Server/CheckHead.py workspace/Sim/out/Soc
fi
if ((vcs_units)); then
    command -v vcs >/dev/null || { echo 'ENV_ERROR: --vcs-units requested but vcs absent'; exit 2; }
    rtl=(Rtl/TpuPkg.sv Rtl/TpuLut.sv Rtl/TpuDot.sv Rtl/TpuDivide.sv Rtl/TpuSqrt.sv Rtl/TpuSram.sv Rtl/TpuRowBuffer.sv Rtl/TpuMatmul.sv Rtl/TpuGelu.sv Rtl/TpuVector.sv Rtl/TpuDma.sv Rtl/TpuAxi.sv Rtl/TpuTop.sv Rtl/TpuNice.sv)
    for top in ArithmeticTest NiceTest; do
        stage="vcs_compile_$top"
        directory="$work/vcs_$top"
        mkdir -p "$directory"
        files=()
        for source in "${rtl[@]}"; do files+=("$work/project/$source"); done
        if ! (cd "$directory"; timeout -k 5 180 vcs -full64 -sverilog -timescale=1ns/1ps -assert svaext \
            "${files[@]}" "$work/project/Sim/$top.sv" -top "$top" -o simv) > "$work/logs/$stage.log" 2>&1; then
            awk '/Error-|Error:|Fatal:/ && !s {s=1} s {print; if(++n==20) exit}' "$work/logs/$stage.log"
            echo "COMPILE_LOG: $work/logs/$stage.log"; exit 1
        fi
        marker='PASS arithmetic:'
        [[ "$top" != NiceTest ]] || marker='PASS NICE:'
        run "vcs_$top" "$marker" 120 "$directory/simv"
    done
fi
stage=complete
{
    echo 'FUNCTIONAL_RESULT: PASS'
    echo 'FOUNDRY_SRAM_STATUS: NOT_BOUND'
    echo 'ASIC_SYNTHESIS_STATUS: NOT_RUN'
    echo 'SPEECH_ACCURACY_STATUS: NOT_EVALUATED'
    echo 'RESULT: COMPLETE (new repository functional reproduction)'
    echo "RESULTS: $work/results.tsv"
    echo "WORK_DIR: $work"
} | tee "$work/summary.txt"
