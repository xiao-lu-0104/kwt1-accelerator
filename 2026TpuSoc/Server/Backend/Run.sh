#!/usr/bin/env bash
# FPGA implementation of the pinned source, not an ASIC macro implementation.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
profile=${1:-soc100}
case "$profile" in
    soc100) top=E203Tpu; tpu=10.000000; cpu=33.333333;;
    soc150) top=E203Tpu; tpu=6.666667; cpu=33.333333;;
    tpu150) top=TpuNiceAxi; tpu=6.666667; cpu=33.333333;;
    *) echo 'Usage: bash Server/Backend/Run.sh [soc100|soc150|tpu150]'; exit 2;;
esac
if [[ -f "$root/MANIFEST.sha256" ]]; then
    (cd "$root"; sha256sum --quiet -c MANIFEST.sha256)
fi
vivado=${VIVADO_BIN:-}
if [[ -z "$vivado" ]]; then vivado=$(command -v vivado || true); fi
if [[ -z "$vivado" ]]; then
    for candidate in /eda/xilinx/vivado2021.1/bin/vivado /eda/xilinx/Vivado/2021.1/bin/vivado; do
        if [[ -x "$candidate" ]]; then vivado=$candidate; break; fi
    done
fi
[[ -n "$vivado" ]] || { echo 'ENV_ERROR: set VIVADO_BIN to the Vivado executable'; exit 2; }
name="Server$(date +%Y%m%dT%H%M%S)-${profile}-$$"
out="$root/workspace/Backend/$name"
mkdir -p "$out"
exec > >(tee "$out/runner.log") 2>&1
echo "PROFILE: $profile; top=$top; TPU period=$tpu ns; CPU period=$cpu ns"
echo 'SCOPE: Artix-7 OOC FPGA internal timing; inferred BRAM; no foundry SRAM/TCM/DDR PHY'
echo "REPORTS: $out"
set +e
timeout -k 30 5400 "$vivado" -mode batch -source "$root/Server/Backend/RunFpga.tcl" \
    -log "$out/Vivado.log" -journal "$out/Vivado.jou" \
    -tclargs "$name" "$top" "$tpu" "$cpu" > "$out/console.log" 2>&1
rc=$?
set -e
if ((rc)); then
    tail -n 35 "$out/console.log"
    echo "RESULT: TOOL_FAIL (exit=$rc; see console.log)"
    exit "$rc"
fi
grep -F 'BACKEND_REPORTS_COMPLETE:' "$out/console.log"
echo 'RESULT: REPORTS_COMPLETE (inspect setup, hold, CDC and bus-skew separately)'
for report in CpuClockSetup CpuClockHold TpuClockSetup TpuClockHold RequestChannelMaxDelay ResponseChannelMaxDelay; do
    if [[ -f "$out/$report.rpt" ]]; then
        echo "CHECK: $report"
        grep -m 1 -E 'Slack \(' "$out/$report.rpt" || true
    fi
done
echo "REPORTS: $out"
