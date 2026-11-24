#!/usr/bin/env bash
set -euo pipefail
tools=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
config=$(realpath "${1:?config required}")
vectors=$(realpath "${2:?evaluation vectors required}")
work=${3:?new work directory required}
mkdir -p "$work"
work=$(realpath "$work")
echo "WORK_DIR=$work"
python3 "$tools/flow.py" preflight --config "$config"
if [[ ! -f "$work/dc_accelerator/Complete.json" ]]; then
    python3 "$tools/flow.py" dc-accelerator --config "$config" --out "$work/dc_accelerator"
fi
if [[ ! -f "$work/dc_system/Complete.json" ]]; then
    python3 "$tools/flow.py" dc-system --config "$config" --accelerator "$work/dc_accelerator" --out "$work/dc_system"
fi
if [[ ! -f "$vectors/Activity.json" ]]; then
    python3 "$tools/flow.py" gate-check --config "$config" --dc "$work/dc_system" --vectors "$vectors"
fi
if [[ ! -f "$work/power/PowerSummary.json" ]]; then
    python3 "$tools/flow.py" power --config "$config" --dc "$work/dc_system" --vectors "$vectors" --out "$work/power"
fi
python3 "$tools/flow.py" pr --config "$config" --dc "$work/dc_system" --out "$work/pr"
echo 'RUN_STAGES_EXECUTED: review DC slack, power activity coverage and PR native reports'
