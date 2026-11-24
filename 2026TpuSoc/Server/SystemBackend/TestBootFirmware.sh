#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out="$root/workspace/Checks/BootGprFix_20261107_v1"
sim="$root/workspace/SharedRuns/local_20261105_ZMFCcR/build/VSharedTest"
vectors="$root/workspace/Server/tpusoc_shared_20261105_v1/Vectors"
[[ -x "$sim" ]] || { echo 'ERROR: original local comparison simulator required'; exit 2; }
for task in encoder ff1; do
    kind=0; directory="$vectors"
    if [[ "$task" == ff1 ]]; then kind=1; directory="$vectors/Ff1_normal"; fi
    [[ ! -e "$out/local_$task.log" ]] || { echo 'ERROR: existing versioned test log'; exit 2; }
    timeout 180 "$sim" +FIRMWARE="$out/fixed/BuildEvidence/Firmware.hex" \
        +VECTORS="$directory" +KIND="$kind" +LAYERS=1 > "$out/local_$task.log" 2>&1
    grep '^PASS SHARED:' "$out/local_$task.log"
done
echo 'PASS LOCAL_BOOT_TASKS: original local CPU comparison simulator, both strict golden results; two-state comparison only, server four-state macro guards still required'
