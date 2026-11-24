#!/usr/bin/env bash
# Run the competition CPU ISA baseline in a fresh, isolated source snapshot.
# Never run "make install", "make clean" or modify the original platform.
set -euo pipefail

platform="${HOME}/soc/e203_hbirdv2-master"
suite=full
tests_dir=""
output_parent="${HOME}/soc"
case_timeout=120
compile_timeout=600
fix_signed_reference=0
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
usage() {
    echo "Usage: bash $0 [--platform DIR] [--suite smoke|full] [--tests-dir DIR] [--output-parent DIR] [--fix-signed-reference]"
}
while (($#)); do
    case "$1" in
        --platform|--suite|--tests-dir|--output-parent)
            (($# >= 2)) || { usage; exit 2; }
            case "$1" in
                --platform) platform=$2;; --suite) suite=$2;;
                --tests-dir) tests_dir=$2;; --output-parent) output_parent=$2;;
            esac
            shift 2;;
        -h|--help) usage; exit 0;;
        --fix-signed-reference) fix_signed_reference=1; shift;;
        *) usage; exit 2;;
    esac
done
[[ "$suite" == smoke || "$suite" == full ]] || { usage; exit 2; }
if ((fix_signed_reference)); then
    command -v python >/dev/null || { echo 'ENV_ERROR: python required for reference-only correction'; exit 2; }
    [[ -f "$script_dir/patch_e203_signed_reference.py" ]] || { echo 'ENV_ERROR: missing reference correction helper'; exit 2; }
fi
for program in vcs make timeout sha256sum cp find sort grep sed awk; do
    command -v "$program" >/dev/null || { echo "ENV_ERROR: missing command $program; source your EDA environment first."; exit 2; }
done
platform=$(cd "$platform" && pwd -P)
tests_dir=${tests_dir:-"$platform/riscv-tools/riscv-tests/isa/generated"}
tests_dir=$(cd "$tests_dir" && pwd -P)
[[ -f "$platform/vsim/bin/run.makefile" ]] || { echo 'ENV_ERROR: missing official run.makefile'; exit 2; }
[[ -f "$tests_dir/rv32ui-p-add.verilog" ]] || { echo 'ENV_ERROR: missing prebuilt rv32ui-p-add.verilog'; exit 2; }
# Whitespace in these paths is unsupported by the official Makefile's recipes.
case "$platform$tests_dir$output_parent" in
    *[[:space:]]*) echo 'ENV_ERROR: use paths without whitespace'; exit 2;;
esac
mkdir -p "$output_parent"
work=$(mktemp -d "$output_parent/cpu_baseline_$(date +%Y%m%d_%H%M%S)_XXXXXX")
mkdir -p "$work/install/rtl" "$work/install/tb" "$work/run"
exec > >(tee "$work/runner.log") 2>&1
echo "WORK_DIR: $work"
echo "PLATFORM: $platform"
echo "SUITE: $suite"
echo "REFERENCE_CHECKER_FIX: $fix_signed_reference (0=original, 1=simulation reference only)"
echo "TESTS_DIR: $tests_dir"
echo "VCS: $(command -v vcs)"

# Retain the competition's existing installed tb_top, including its vcs define.
# The previous comparison established that installed RTL equals source RTL.
if [[ -f "$platform/vsim/install/rtl/core/config.v" && -f "$platform/vsim/install/tb/tb_top.v" ]]; then
    source_rtl="$platform/vsim/install/rtl"
    source_tb="$platform/vsim/install/tb"
    echo 'SNAPSHOT_SOURCE: competition vsim/install'
else
    source_rtl="$platform/rtl/e203"
    source_tb="$platform/tb"
    echo 'SNAPSHOT_SOURCE: competition rtl/e203 and tb (no installed copy)'
fi
cp -a "$source_rtl/." "$work/install/rtl/"
cp -a "$source_tb/." "$work/install/tb/"
cp "$platform/vsim/bin/run.makefile" "$work/run/Makefile"
grep -q -- '+define+FPGA' "$work/run/Makefile" || {
    echo 'ENV_ERROR: expected competition VCS +define+FPGA option is absent; review platform version.'; exit 2;
}
{
    echo "platform=$platform"
    echo "snapshot_rtl=$source_rtl"
    echo "snapshot_tb=$source_tb"
    echo "test_dir=$tests_dir"
    echo "suite=$suite"
    echo "reference_checker_fix=$fix_signed_reference"
    echo "date=$(date -u +%FT%TZ)"
    echo "uname=$(uname -a)"
    echo "vcs=$(command -v vcs)"
    echo "case_timeout_seconds=$case_timeout"
    echo "compile_timeout_seconds=$compile_timeout"
} > "$work/environment.txt"
(
    cd "$work"
    find install -type f -print0 | sort -z | xargs -0 sha256sum
    sha256sum run/Makefile
) > "$work/snapshot_before_compile.sha256"
if ((fix_signed_reference)); then
    python "$script_dir/patch_e203_signed_reference.py" \
        --file "$work/install/rtl/core/e203_exu_alu_muldiv.v" \
        --record "$work/reference_checker_patch.json"
    (
        cd "$work"
        find install -type f -print0 | sort -z | xargs -0 sha256sum
        sha256sum run/Makefile
    ) > "$work/snapshot_after_reference_fix.sha256"
fi

families=(rv32ui-p rv32um-p rv32ua-p rv32uc-p rv32mi-p)
selected=(rv32ui-p-add)
missing_groups=0
: > "$work/test_groups.tsv"
shopt -s nullglob
if [[ "$suite" == full ]]; then
    for family in "${families[@]}"; do
        files=("$tests_dir"/"$family"*.verilog)
        printf '%s\t%d\n' "$family" "${#files[@]}" >> "$work/test_groups.tsv"
        if ((${#files[@]} == 0)); then
            echo "MISSING_GROUP: $family"
            missing_groups=$((missing_groups+1))
        fi
        for file in "${files[@]}"; do
            name=${file##*/}; name=${name%.verilog}
            [[ "$name" == rv32ui-p-add ]] || selected+=("$name")
        done
    done
fi
printf '%s\n' "${selected[@]}" > "$work/selected_tests.txt"
for name in "${selected[@]}"; do sha256sum "$tests_dir/$name.verilog"; done > "$work/test_images.sha256"
echo "SELECTED_TESTS: ${#selected[@]} (rv32ui-p-add runs first)"

make_args=(-C "$work/run" "RUN_DIR=$work/run" "VSRC_DIR=$work/install/rtl"
           "VTB_DIR=$work/install/tb" SIM_TOOL=vcs SHELL=/bin/bash '.SHELLFLAGS=-e -o pipefail -c')
echo 'COMPILING: fresh snapshot, no cached compile.flg or simv'
build_rc=0
timeout -k 15s "${compile_timeout}s" make "${make_args[@]}" compile > "$work/build.log" 2>&1 || build_rc=$?
if ((build_rc != 0)) || [[ ! -x "$work/run/simv" ]] || grep -Eq 'Error-\[|^Error:|^Fatal:' "$work/build.log"; then
    echo "COMPILE_FAIL: command_exit=$build_rc"
    tail -n 65 "$work/build.log"
    echo "BUILD_LOG: $work/build.log"
    exit 1
fi
echo 'COMPILE_PASS: fresh simv generated'
sha256sum "$work/install/tb/tb_top.v" > "$work/tb_after_official_compile.sha256"
printf 'test\tstatus\texit\twall_seconds\tlog\n' > "$work/results.tsv"
passed=0
failed=0
for name in "${selected[@]}"; do
    echo "RUN: $name"
    start_seconds=$SECONDS
    rc=0
    timeout -k 10s "${case_timeout}s" make "${make_args[@]}" run DUMPWAVE=0 \
        "TESTCASE=$tests_dir/$name" > "$work/$name.driver.log" 2>&1 || rc=$?
    log="$work/run/$name/$name.log"
    status=FAIL
    if ((rc == 124 || rc == 137)); then
        status=WALL_TIMEOUT
    elif ((rc == 0)) && [[ -f "$log" ]] \
        && [[ $(grep -c 'Test Result Summary' "$log" || true) == 1 ]] \
        && [[ $(grep -c 'TEST_PASS' "$log" || true) == 1 ]] \
        && grep -Fq "$tests_dir/$name" "$log" \
        && ! grep -Eiq 'TEST_FAIL|Time[[:space:]]+Out|^Error:|^Fatal:|Error-\[|\$readmemh.*(error|unable|cannot)|Unable to open|cannot be opened' "$log"; then
        status=PASS
    fi
    elapsed=$((SECONDS-start_seconds))
    printf '%s\t%s\t%d\t%d\t%s\n' "$name" "$status" "$rc" "$elapsed" "$log" >> "$work/results.tsv"
    if [[ "$status" == PASS ]]; then
        passed=$((passed+1))
        echo "PASS: $name (${elapsed}s)"
    else
        failed=$((failed+1))
        echo "$status: $name (exit=$rc)"
        tail -n 30 "$work/$name.driver.log"
        [[ ! -f "$log" ]] || tail -n 25 "$log"
        if [[ "$name" == rv32ui-p-add ]]; then
            echo 'SMOKE_FAILED: stopping before the remaining ISA tests.'
            break
        fi
    fi
done
echo '================ CPU BASELINE SUMMARY ================'
echo "PASSED=$passed FAILED=$failed SELECTED=${#selected[@]} MISSING_GROUPS=$missing_groups"
echo "REFERENCE_CHECKER_FIX=$fix_signed_reference"
echo "RESULTS: $work/results.tsv"
echo "WORK_DIR: $work"
if ((failed > 0)); then
    echo 'RESULT: FAIL'; exit 1
elif ((missing_groups > 0 || passed != ${#selected[@]})); then
    echo 'RESULT: INCOMPLETE (available tests passed; required test groups are missing)'; exit 2
else
    echo "RESULT: PASS ($suite suite; competition behavior-memory simulation, not macro timing signoff)"
fi
