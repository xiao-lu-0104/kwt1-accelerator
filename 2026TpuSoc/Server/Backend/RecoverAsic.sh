#!/usr/bin/env bash
# v3b recovery: remove one unused REAL parameter, reuse verified VCS/DB evidence.
# Never modifies the original project, logs, libraries or failed run directory.
set -euo pipefail
if [[ $# != 2 || "$1" != --run-dir ]]; then
    echo 'Usage: bash RecoverAsic.sh --run-dir ORIGINAL_V3B_WORK_DIR'; exit 2
fi
original=$(cd "$2" && pwd -P)
for required in project package_manifest.sha256 reviewed_binding.json library_sha256.txt logs/vcs_run_SpBindingTest.log logs/vcs_run_CdcTest.log logs/library.log; do
    [[ -e "$original/$required" ]] || { echo "ENV_ERROR: missing $original/$required"; exit 2; }
done
if command -v python3 >/dev/null; then py=python3; else py=python; fi
work=$(mktemp -d "$original/synth_recovery_20261102_XXXXXX")
mkdir -p "$work/logs"
exec > >(tee "$work/runner.log") 2>&1
stage=verify_reuse
trap 'rc=$?; if ((rc)); then echo "RESULT: FAIL (stage=$stage exit=$rc)"; echo "RECOVERY_DIR: $work"; fi' EXIT
echo 'RECOVERY_REVISION: v3c_remove_unused_real_parameter'
echo "ORIGINAL_RUN: $original"
echo "RECOVERY_DIR: $work"
"$py" - "$original" "$work" <<'PY'
from __future__ import print_function
import hashlib
import json
import os
import shutil
import sys

original, work = sys.argv[1:]
def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            data = stream.read(1024*1024)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()
def read(path):
    with open(path, 'rb') as stream:
        return stream.read()
manifest = os.path.join(original, 'package_manifest.sha256')
if sha(manifest) != 'a772a687ea047de934d60d38d984fc4f0b2bd7f6a4ecb3d401f8bc61ab9b6d84':
    raise ValueError('This recovery requires the exact v3b package manifest')
entries = {}
for line in read(manifest).decode('ascii').splitlines():
    digest, relative = line.split(None, 1)
    entries[relative] = digest
project = os.path.join(original, 'project')
for folder, dirs, names in os.walk(project):
    for name in names:
        path = os.path.join(folder, name)
        relative = os.path.relpath(path, project).replace(os.sep, '/')
        if os.path.islink(path) or entries.get(relative) != sha(path):
            raise ValueError('Original project differs from tested v3b: ' + relative)
for relative in entries:
    if relative.startswith(('Rtl/', 'Server/', 'Sim/', 'e203_hbirdv2/')):
        if not os.path.isfile(os.path.join(project, *relative.split('/'))):
            raise ValueError('Original project input missing: ' + relative)
checks = [('logs/vcs_run_SpBindingTest.log', b'PASS SP_BINDING:'),
          ('logs/vcs_run_CdcTest.log', b'PASS CDC:'),
          ('logs/library.log', b'SP_LIBRARY_COMPLETE:')]
for relative, marker in checks:
    if marker not in read(os.path.join(original, *relative.split('/'))):
        raise ValueError('Missing passing evidence: ' + relative)
libraries = []
for line in read(os.path.join(original, 'library_sha256.txt')).decode('utf-8').splitlines():
    digest, path = line.split(None, 1)
    if not os.path.isfile(path) or sha(path) != digest:
        raise ValueError('Cached library differs from previous run: ' + path)
    libraries.append(path)
spdb = os.path.join(original, 'sram_db', 'RAMSP1024X16_tt_1p10v_1p10v_25c.db')
standard = [path for path in libraries if path != spdb]
if spdb not in libraries or len(standard) != 1:
    raise ValueError('Expected one cached SRAM DB and one standard-cell DB')
with open(os.path.join(work, 'StdDb.txt'), 'w') as stream:
    stream.write(standard[0] + '\n')
shutil.copytree(project, os.path.join(work, 'project'))
adapter = os.path.join(work, 'project', 'Server', 'Backend', 'SpFoundry.sv')
before = read(adapter)
old = b'    parameter AW = $clog2(DEPTH),\n    parameter real TCO = 1.25\n'
new = b'    parameter AW = $clog2(DEPTH)\n'
if before.count(old) != 1:
    raise ValueError('Expected exactly the unused TCO declaration from v3b')
after = before.replace(old, new)
with open(adapter, 'wb') as stream:
    stream.write(after)
record = dict(original_run=original, change='Remove unused REAL TCO; no connections/logic changed',
              old_adapter_sha256=hashlib.sha256(before).hexdigest(),
              new_adapter_sha256=hashlib.sha256(after).hexdigest(),
              reused_vcs_and_library_checks=checks[0][0:1]+checks[1][0:1]+checks[2][0:1],
              cached_libraries=libraries)
with open(os.path.join(work, 'recovery.json'), 'w') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print('REUSE_VERIFIED: v3b source, passing vendor/CDC tests and exact cached DB hashes')
print('PATCH: remove unused REAL TCO declaration only')
PY
export TPU_ASIC_ROOT="$work/project"
export TPU_SRAM_ROOT=${SRAM_LIBRARY_ROOT:-/storage1/admin_public_dir/SRAM_Lib_2025}
export TPU_STDCELL_DB
TPU_STDCELL_DB=$(cat "$work/StdDb.txt")
export TPU_SRAM_DB="$original/sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db"
export TPU_CPU_PERIOD=6.666667
"$py" "$TPU_ASIC_ROOT/Server/Backend/VerifyMacro.py" "$TPU_SRAM_ROOT" "$work/reviewed_binding.json"
cp "$0" "$work/RecoverAsic.sh"
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo "ENV_ERROR: missing executable $dc_bin"; exit 2; }
export PATH="$(dirname "$dc_bin"):$PATH"
echo 'REUSED: passing actual vendor macro function test, CDC test, converted TT SRAM DB'
echo 'TARGET: TPU=150MHz; CPU=150MHz; constraints unchanged; 30-minute limit per top'
for top in TpuNiceAxi E203Tpu; do
    export TPU_ASIC_TOP="$top"
    export TPU_ASIC_OUT="$work/$top"
    stage="synthesis_$top"
    echo "RUN: $stage; log=$work/logs/$top.log"
    if ! (cd "$work"; timeout -k 30 1800 "$dc_bin" -f "$TPU_ASIC_ROOT/Server/Backend/RunAsic.tcl") > "$work/logs/$top.log" 2>&1; then
        tail -n 55 "$work/logs/$top.log"; exit 1
    fi
    grep -q '^ASIC_REPORTS_COMPLETE:' "$work/logs/$top.log" || { tail -n 55 "$work/logs/$top.log"; exit 1; }
    if grep -Eq '^(Error:|ASIC_ERROR:)' "$work/logs/$top.log"; then tail -n 55 "$work/logs/$top.log"; exit 1; fi
    cat "$TPU_ASIC_OUT/summary.txt"
done
stage=complete
echo 'RESULT: REPORTS_COMPLETE (inspect setup/hold/CDC statuses separately)'
echo "RECOVERY_DIR: $work"
