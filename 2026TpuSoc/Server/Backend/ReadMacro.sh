#!/usr/bin/env bash
# Collect the actual single-port macro interface before adding an ASIC binding.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
base=${SRAM_LIBRARY_ROOT:-/storage1/admin_public_dir/SRAM_Lib_2025}
if [[ -f "$root/MANIFEST.sha256" ]]; then
    (cd "$root"; sha256sum --quiet -c MANIFEST.sha256)
fi
if command -v python3 >/dev/null; then py=python3; else py=python; fi
mkdir -p "$HOME/soc"
out=$(mktemp -d "$HOME/soc/tpusoc_sp_audit_XXXXXX")
exec > >(tee "$out/runner.log") 2>&1
echo "WORK_DIR: $out"
echo 'MODE: read-only RAMSP1024X16 interface and datasheet audit; no synthesis'
timeout -k 5 120 "$py" "$root/Server/Backend/audit_kwt_sp_macro.py" \
    --root "$base" --out-dir "$out/macro"
# Extracted text remains private on the server. Show only relevant excerpts.
set +e
timeout -k 5 120 "$py" "$root/Server/Backend/read_kwt_sram_datasheets.py" \
    --root "$base" --macro RAMSP1024X16 --max-docs 1 --out-dir "$out/datasheet" \
    > "$out/datasheet.log" 2>&1
doc_rc=$?
set -e
cat "$out/datasheet.log"
echo "DATASHEET_TOOL_EXIT: $doc_rc"
echo "WORK_DIR: $out"
