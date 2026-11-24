"""Regenerate frozen task vectors and archive matching numerical-model raw material locally."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[2]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    bundle=ROOT/'workspace/Server/tpusoc_shared_20261105_v1'
    if sha(bundle/'MANIFEST.sha256')!='baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83':
        raise ValueError('Wrong frozen task bundle')
    for line in (bundle/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1)
        frozen=bundle/name
        if sha(frozen)!=digest: raise ValueError('Frozen bundle changed: '+name)
        if name.startswith(('Rtl/','Sw/','Backend/')) and sha(ROOT/name)!=digest:
            raise ValueError('Current design differs from passed task bundle: '+name)
    out=Path(tempfile.mkdtemp(prefix='InitialNumerics_20261106_',dir=ROOT/'workspace/Checks'))
    model=ROOT/'workspace/Model/official'; ff1=ROOT/'workspace/Sim/out/Ff1'
    inputs=[p for p in sorted((ROOT/'Model').glob('*')) if p.is_file() and p.suffix in ('.py','.txt')]
    inputs += [p for p in sorted(model.rglob('*')) if p.is_file()]
    inputs += [p for p in sorted(ff1.rglob('*')) if p.is_file() and p.suffix in ('.bin','.txt')]
    before={str(p):sha(p) for p in inputs}
    with (out/'regenerate.log').open('x') as log:
        subprocess.run([sys.executable,str(ROOT/'Model/MakeSharedVectors.py'),'--model',str(model),
            '--ff1',str(ff1),'--out',str(out/'Vectors')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    expected={p.relative_to(bundle/'Vectors').as_posix():sha(p) for p in sorted((bundle/'Vectors').rglob('*.hex'))}
    actual={p.relative_to(out/'Vectors').as_posix():sha(p) for p in sorted((out/'Vectors').rglob('*.hex'))}
    if not expected or actual!=expected: raise ValueError('Regenerated vectors differ from passed server task bundle; see '+str(out))
    if any(sha(Path(p))!=digest for p,digest in before.items()): raise ValueError('Numerical input changed during regeneration')
    material=out/'NumericalMaterial'; material.mkdir()
    shutil.copytree(ROOT/'Model',material/'Model',ignore=shutil.ignore_patterns('.venv','__pycache__','*.pyc'))
    shutil.copytree(model,material/'ExtractedOfficialParameters')
    (material/'Doc').mkdir()
    for name in ('Implementation.md','Precision.md','ThirdParty.md','Ff1.md','SharedSram.md'):
        shutil.copy2(ROOT/'Doc'/name,material/'Doc'/name)
    record={'scope':'initial numerical-source raw material; frozen vector reproducibility only',
        'frozen_bundle_manifest_sha256':sha(bundle/'MANIFEST.sha256'),'matched_hex_files':len(actual),
        'inputs':before,'vector_sha256':actual,
        'acceptance':'not the official 600-sample score; system PPA/final submission package still pending'}
    (material/'NumericalMaterial.json').write_text(json.dumps(record,indent=2)+'\n')
    (material/'STATUS.txt').write_text('PARTIAL INITIAL RAW MATERIAL SUPPLEMENT\n'
        'Current RTL/driver hashes match the passed source bundle. Current numerical code regenerated all task HEX files byte-identically.\n'
        'Contains numerical source, parameter-conversion scripts, dependency lists and exported official layer parameters.\n'
        'Not a 600-sample precision result, a classification-accuracy result, or a complete portable submission package.\n'
        'Join with the server raw reports/archive and finish clean reproduction.\n')
    (material/'MANIFEST.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(material).as_posix()+'\n'
        for p in sorted(material.rglob('*')) if p.is_file()))
    package=out/'NumericalMaterial.partial.tar.gz'
    with tarfile.open(package,'x:gz') as stream:
        for path in sorted(material.rglob('*')):
            if path.is_file(): stream.add(path,arcname='NumericalMaterial/'+path.relative_to(material).as_posix(),recursive=False)
    print('NUMERICAL_MATERIAL_PASS: matched_hex_files='+str(len(actual)))
    print('NUMERICAL_MATERIAL_ARCHIVE:',package)
    print('SHA256:',sha(package))


if __name__=='__main__': main()
