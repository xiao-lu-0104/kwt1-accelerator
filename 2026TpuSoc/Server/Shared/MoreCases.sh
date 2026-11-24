#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"
[[ $# == 1 ]] || { echo 'Usage: MoreCases.sh workspace/SharedRuns/<local run>'; exit 2; }
work=$(cd "$1" && pwd -P)
[[ "$work" == "$root/workspace/SharedRuns/"* && -f "$work/SourceInputs.json" ]] || exit 2
python3 Server/Shared/Snapshot.py "$work" --verify
for name in normal zero extreme Layer{1..11}; do
    "$work/build/VSharedTest" +FIRMWARE="$work/Firmware.hex" \
        +VECTORS="$root/workspace/Sim/out/Shared/Ff1_$name" +KIND=1 +LAYERS=1 > "$work/ff1_$name.log"
    grep '^PASS SHARED:' "$work/ff1_$name.log"
done
python3 Server/Shared/Snapshot.py "$work" --verify
