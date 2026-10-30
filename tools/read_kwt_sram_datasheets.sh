#!/usr/bin/env bash
# Read shared datasheets; create private evidence only. No EDA tool is invoked.
set -euo pipefail
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
for program in python timeout sha256sum; do
    command -v "$program" >/dev/null || { echo "ENV_ERROR: missing $program"; exit 2; }
done
if [[ -f "$package_root/MANIFEST.sha256" ]]; then
    (cd "$package_root"; sha256sum --quiet -c MANIFEST.sha256)
fi
echo 'REVISION: 20261030_v2_postscript'
echo 'RUN: read RAMTP datasheets; 120-second limit plus 5-second exit grace; no synthesis'
timeout -k 5 120 python "$package_root/tools/read_kwt_sram_datasheets.py" "$@"
