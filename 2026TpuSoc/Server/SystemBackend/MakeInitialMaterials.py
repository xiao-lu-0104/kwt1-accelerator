"""Build a small inbound-only numerical supplement and server-side merge entry."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NUMERICAL = ROOT / 'workspace/Checks/InitialNumerics_20261106_hrz58ess/NumericalMaterial'
BACKEND_SHA = '0c4d86a28160769abeaedfcc832368723dbbcb61509767f716f86aabfd390fe3'
NUMERICAL_SHA = 'd6d63bb158523bb3423c735f6d793a54e613c29b4bd29c253ca3a7656ffb3b1b'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build_files():
    from InitialMaterials import verify
    original_entries = verify(NUMERICAL)
    full = NUMERICAL.parent / 'NumericalMaterial.partial.tar.gz'
    if sha(full.read_bytes()) != NUMERICAL_SHA:
        raise ValueError('Original numerical archive changed')
    files = {}
    for label, target in (('Model', 'Model'), ('Doc', 'NumericalDocs')):
        for path in sorted((NUMERICAL / label).rglob('*')):
            if path.is_file():
                files[target + '/' + path.relative_to(NUMERICAL / label).as_posix()] = path.read_bytes()
    files['NumericalMaterial.json'] = (NUMERICAL / 'NumericalMaterial.json').read_bytes()
    parameter_manifest = json.loads((NUMERICAL / 'ExtractedOfficialParameters/Manifest.json').read_text(encoding='utf-8'))
    parameter_manifest['original_full_numerical_archive_sha256'] = NUMERICAL_SHA
    parameter_manifest['omitted_extracted_parameter_sha256'] = {
        name: digest for name, digest in original_entries.items() if name.startswith('ExtractedOfficialParameters/')}
    parameter_manifest['transfer_scope'] = (
        'Numerical source and conversion tools only. Extracted floating-point parameter arrays remain local; '
        'server uses unchanged quantized HEX vectors and records the pinned external checkpoint source.')
    files['ParameterSources.json'] = (json.dumps(parameter_manifest, indent=2) + '\n').encode()
    for name in ('CheckSharedHex.py', 'CheckInitialMaterials.py'):
        files[name] = (HERE / name).read_bytes().replace(b'\r\n', b'\n')
    for name in ('初赛技术报告_20261105_草稿.md', '面积分配_20261106.md', '功耗原始报告_20261107.md',
                 '后端材料包预览_20261107.md', '本科初赛原始材料收尾_20261106.md'):
        files['CurrentDocs/' + name] = (ROOT / 'Doc' / name).read_bytes()
    files['Supplement.json'] = (json.dumps({
        'scope': 'Inbound source supplement, not a transfer of the full floating-point data archive',
        'backend_archive_sha256': BACKEND_SHA, 'original_numerical_archive_sha256': NUMERICAL_SHA,
        'submission_channel': 'UNCONFIRMED; no outbound transfer attempted',
        'official_accuracy': 'NOT_ESTABLISHED',
        'model_replay': 'Frozen quantized HEX only; local 15 FF1 and 12 encoder-layer results match.'}, indent=2) + '\n').encode()
    files['MANIFEST.sha256'] = ''.join(sha(data) + '  ' + name + '\n'
        for name, data in sorted(files.items())).encode()
    return files


def render(files):
    parts = ['''#!/usr/bin/env bash
set -euo pipefail
backend=$(python3 - "$HOME/soc" <<'TPUSOC_SELECT_BACKEND'
from pathlib import Path
import sys
for path in sorted(Path(sys.argv[1]).glob('tpusoc_backend_materials_20261107_*'), key=lambda p:p.stat().st_mtime, reverse=True):
    proof=path/'BackendRawMaterials.sha256'
    if proof.is_file() and proof.read_text().split()[0]=='BACKEND_DIGEST':
        print(path); break
else: raise SystemExit('ERROR: the successful verified backend package is required')
TPUSOC_SELECT_BACKEND
)
work=$(mktemp -d "$HOME/soc/tpusoc_initial_materials_20261107_XXXXXX")
mkdir -p "$work/tools" "$work/supplement"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: INITIAL_MATERIAL_MERGE_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo "BACKEND_SOURCE: $backend"
echo 'MODE: inbound numerical sources + existing server backend; no download, DC, synthesis or simulation'
echo 'LIMIT: verify/copy/model replay/archive 15min; model execution 5min cap; no dependency installation'
'''.replace('BACKEND_DIGEST', BACKEND_SHA)]
    payloads = {'supplement/' + name: data for name, data in files.items()}
    for name in ('InitialMaterials.py', 'StageWatch.py'):
        payloads['tools/' + name] = (HERE / name).read_bytes().replace(b'\r\n', b'\n')
    for index, (name, data) in enumerate(sorted(payloads.items())):
        encoded = base64.b64encode(gzip.compress(data, mtime=0)).decode()
        marker = 'TPUSOC_INITIAL_SOURCE_' + str(index)
        parts.append('python3 - "$work/' + name + '" <<\'' + marker + "'\n" +
            'import base64,gzip,hashlib,sys\nfrom pathlib import Path\n' +
            'data=gzip.decompress(base64.b64decode("' + encoded + '"))\n' +
            'assert hashlib.sha256(data).hexdigest()=="' + sha(data) + '"\n' +
            'path=Path(sys.argv[1]); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)\n' + marker + '\n')
    parts.append('''export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$work/tools"
if ! python3 -B -u "$work/tools/StageWatch.py" --label merge_initial_materials --limit 900 --log "$work/merge.log" --cwd "$work" -- \\
    python3 -B -u "$work/tools/InitialMaterials.py" "$work" --backend "$backend" --supplement "$work/supplement" --backend-sha256 BACKEND_DIGEST; then
    tail -n 25 "$work/merge.log"; exit 1
fi
cat "$work/merge.log"
echo "WORK_DIR: $work"
'''.replace('BACKEND_DIGEST', BACKEND_SHA))
    return ''.join(parts).encode()


def main():
    files = build_files()
    data = render(files)
    output = ROOT / 'workspace/Server/tpusoc_initial_materials_20261107_v3.sh'
    if output.exists() and output.read_bytes() != data:
        raise ValueError('Refusing to replace versioned artifact')
    output.write_bytes(data)
    digest = sha(data)
    payload = base64.b64encode(gzip.compress(data, mtime=0)).decode()
    code = ('import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("' +
        payload + '")); assert hashlib.sha256(d).hexdigest()=="' + digest +
        '"; p=Path.home()/"Desktop"/"' + output.name +
        '"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); '+
        'print("LOCAL_TRANSFER_OK SHA256=' + digest + '",flush=True); os.execvp("bash",["bash",str(p)])')
    paste = "python3 -c '" + code + "'\n"
    if len(paste.encode()) > 110000:
        raise ValueError('Paste payload exceeds the bounded single-command transfer size')
    output.with_suffix('.paste.txt').write_text(paste, encoding='utf-8')
    print('ARTIFACT', output, 'BYTES', len(data), 'SHA256', digest, 'PASTE_BYTES', len(paste.encode()))
    print('SUPPLEMENT_FILES', len(files), 'SUPPLEMENT_BYTES', sum(len(value) for value in files.values()))


if __name__ == '__main__':
    main()
