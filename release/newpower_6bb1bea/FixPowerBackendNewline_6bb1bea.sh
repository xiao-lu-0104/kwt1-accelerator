#!/usr/bin/env bash
set -euo pipefail
python3 - <<'FIX_CRLF'
from pathlib import Path
import hashlib,json,os
root=Path('/tmp/final_power_6bb1bea_'+str(os.getuid()))
accroot=Path('/tmp/final_dc_6bb1bea_'+str(os.getuid()))
manifest_path=root/'PowerManifest.json'
manifest=json.loads(manifest_path.read_text())
assert manifest['source_commit']=='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6', 'Wrong power revision'
def digest(b):return hashlib.sha256(b).hexdigest()
for name,expected in manifest['files_sha256'].items():
    p=(root/name).resolve()
    assert root.resolve() in p.parents and digest(p.read_bytes())==expected, 'Power input changed: '+name
source_manifest=json.loads((accroot/'SourceManifest.json').read_text())
assert source_manifest['source_commit']==manifest['source_commit'], 'DC source revision mismatch'
backend_name='source/Backend/E203TpuBackend.sv'
raw=(accroot/backend_name).read_bytes()
assert digest(raw)==source_manifest['files_sha256'][backend_name], 'Original DC backend was changed'
canonical=digest(raw.replace(b'\r\n',b'\n'))
assert canonical==manifest['original_backend_sha256']=='743dc74d7214c91f732f3f6817313095c6acb4de74502dbeccd1870ed3d56601', 'Substantive backend difference: stop'
runner=root/'tools/RunPower.py'
previous=runner.read_bytes()
OLD_SHA='b206837613e59050cd63e22708ed1259f2416ec3f5adcde6c25534261d42ebc1'
NEW_SHA='4b23baac9e425792ece50627ba19a333aa4995eac8bc9c3558d2ed00435f9783'
if digest(previous)==NEW_SHA:
    print('CRLF_FIX_ALREADY_APPLIED')
else:
    assert digest(previous)==OLD_SHA, 'Unexpected runner version: stop'
    old_line="    if sha(accroot/'source/Backend/E203TpuBackend.sv')!=manifest['original_backend_sha256']:raise ValueError('System adapter belongs to another backend')"
    new_lines="    backend_bytes=(accroot/'source/Backend/E203TpuBackend.sv').read_bytes()\n    backend_sha=hashlib.sha256(backend_bytes.replace(b'\\r\\n',b'\\n')).hexdigest()\n    if backend_sha!=manifest['original_backend_sha256']:raise ValueError('System adapter belongs to another backend')"
    text=previous.decode('utf-8')
    assert text.count('import gzip\n')==1 and text.count(old_line)==1, 'Patch anchor changed'
    patched=text.replace('import gzip\n','import gzip\nimport hashlib\n',1).replace(old_line,new_lines,1).encode('utf-8')
    assert digest(patched)==NEW_SHA, 'Patched runner differs from reviewed version'
    for path,data in [(root/'PowerManifest.before_crlf_fix.json',manifest_path.read_bytes()),(root/'tools/RunPower.before_crlf_fix.py',previous)]:
        if path.exists():assert path.read_bytes()==data, 'Unexpected backup '+str(path)
        else:path.write_bytes(data)
    runner.write_bytes(patched)
    manifest['files_sha256']['tools/RunPower.py']=NEW_SHA
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    evidence={'reason':'DC Git archive CRLF versus canonical LF; normalize CRLF only after original source hash is checked',
              'raw_backend_sha256':digest(raw),'canonical_backend_sha256':canonical,'old_runner_sha256':OLD_SHA,'new_runner_sha256':NEW_SHA}
    (root/'BackendNewlineFix.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print('BACKEND_CRLF_CANONICAL_CHECK_FIXED')
print('ORIGINAL_DC_SOURCE_UNCHANGED; CACHE_AND_NETLIST_PRESERVED')
FIX_CRLF
root="/tmp/final_power_6bb1bea_$(id -u)"
exec > >(tee -a "$root/runner.log") 2>&1
python3 -u "$root/tools/RunPower.py" "$root"
