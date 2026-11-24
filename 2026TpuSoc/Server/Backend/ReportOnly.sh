#!/usr/bin/env bash
# Recover reports from v3c mapped DDCs without repeating synthesis.
set -euo pipefail
if [[ $# != 2 || "$1" != --recovery-dir ]]; then
    echo 'Usage: bash ReportOnly.sh --recovery-dir V3C_SYNTH_RECOVERY_DIR'; exit 2
fi
previous=$(cd "$2" && pwd -P)
for name in recovery.json StdDb.txt TpuNiceAxi/TpuNiceAxi_mapped.ddc E203Tpu/E203Tpu_mapped.ddc; do
    [[ -s "$previous/$name" ]] || { echo "ENV_ERROR: missing $previous/$name"; exit 2; }
done
if command -v python3 >/dev/null; then py=python3; else py=python; fi
work=$(mktemp -d "$previous/report_recovery_20261102_XXXXXX")
mkdir -p "$work/logs" "$work/tools"
exec > >(tee "$work/runner.log") 2>&1
stage=verify_checkpoint_inputs
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "REPORT_DIR: $work"; fi' EXIT
echo 'REPORT_REVISION: v3d_numeric_min_pin_endpoints_leaf_area'
echo "PREVIOUS_RECOVERY: $previous"
echo "REPORT_DIR: $work"
# __REPORT_TOOLS__
"$py" - "$previous" "$work" <<'PY'
from __future__ import print_function
import hashlib
import json
import os
import sys
previous, work = sys.argv[1:]
def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            data = stream.read(1024*1024)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()
with open(os.path.join(previous, 'recovery.json')) as stream:
    recovery = json.load(stream)
original = recovery['original_run']
manifest = os.path.join(original, 'package_manifest.sha256')
if sha(manifest) != 'a772a687ea047de934d60d38d984fc4f0b2bd7f6a4ecb3d401f8bc61ab9b6d84':
    raise ValueError('Expected original v3b source manifest')
libraries = []
with open(os.path.join(original, 'library_sha256.txt')) as stream:
    for line in stream:
        digest, path = line.strip().split(None, 1)
        if sha(path) != digest:
            raise ValueError('Cached library changed: ' + path)
        libraries.append(dict(path=path, sha256=digest))
spdb = os.path.join(original, 'sram_db', 'RAMSP1024X16_tt_1p10v_1p10v_25c.db')
standard = [lib['path'] for lib in libraries if lib['path'] != spdb]
if len(standard) != 1 or not any(lib['path'] == spdb for lib in libraries):
    raise ValueError('Expected standard and SRAM libraries')
for name, value in [('VerifiedStdDb.txt', standard[0]), ('VerifiedSpDb.txt', spdb)]:
    with open(os.path.join(work, name), 'w') as stream:
        stream.write(value+'\n')
inputs = []
for top in ['TpuNiceAxi', 'E203Tpu']:
    path = os.path.join(previous, top, top+'_mapped.ddc')
    inputs.append(dict(top=top, path=path, sha256=sha(path)))
with open(os.path.join(work, 'inputs.json'), 'w') as stream:
    json.dump(dict(previous=previous, libraries=libraries, checkpoints=inputs), stream, indent=2)
    stream.write('\n')
print('CHECKPOINT_INPUTS_VERIFIED: cached libraries hashed; original DDC fingerprints recorded')
PY
export TPU_REPORT_TOOLS="$work/tools"
export TPU_STDCELL_DB
TPU_STDCELL_DB=$(cat "$work/VerifiedStdDb.txt")
export TPU_SRAM_DB
TPU_SRAM_DB=$(cat "$work/VerifiedSpDb.txt")
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo "ENV_ERROR: missing $dc_bin"; exit 2; }
export PATH="$(dirname "$dc_bin"):$PATH"
for top in TpuNiceAxi E203Tpu; do
    export TPU_ASIC_TOP="$top"
    export TPU_ASIC_OUT="$work/$top"
    export TPU_REPORT_DDC="$previous/$top/${top}_mapped.ddc"
    stage="report_$top"
    echo "RUN: $stage; report-only 15-minute limit; log=$work/logs/$top.log"
    if ! (cd "$work"; timeout -k 15 900 "$dc_bin" -f "$work/tools/ReportCheckpoint.tcl") > "$work/logs/$top.log" 2>&1; then
        tail -n 60 "$work/logs/$top.log"; exit 1
    fi
    grep -q '^CHECKPOINT_REPORT_COMPLETE:' "$work/logs/$top.log" || { tail -n 60 "$work/logs/$top.log"; exit 1; }
    if grep -Eq '^(Error:|ASIC_REPORT_ERROR:)' "$work/logs/$top.log"; then tail -n 60 "$work/logs/$top.log"; exit 1; fi
    cat "$TPU_ASIC_OUT/summary.txt"
    for group in TpuClock CpuClock; do
        for kind in setup hold; do
            report="$TPU_ASIC_OUT/${group}_internal_${kind}.rpt"
            if [[ -f "$report" ]]; then
                echo "KEY_PATH: $top $group internal $kind"
                awk '/Startpoint:|Endpoint:|slack \(/ {print; if (++n == 3) exit}' "$report"
            fi
        done
    done
done
"$py" - "$work/inputs.json" <<'PY'
import hashlib, json, sys
with open(sys.argv[1]) as stream:
    inputs = json.load(stream)
for entry in inputs['checkpoints']:
    digest = hashlib.sha256()
    with open(entry['path'], 'rb') as stream:
        while True:
            data = stream.read(1024*1024)
            if not data:
                break
            digest.update(data)
    if digest.hexdigest() != entry['sha256']:
        raise ValueError('Original mapped DDC changed: '+entry['path'])
print('ORIGINAL_DDCS_UNCHANGED: hash verified after reporting')
PY
stage=complete
echo 'RESULT: REPORTS_COMPLETE (corrected summaries; inspect real failures; no netlist reoptimization)'
echo "REPORT_DIR: $work"
