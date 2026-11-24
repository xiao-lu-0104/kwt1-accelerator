"""Package current reviewed worktree and offline vectors; never export pinned old RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True, help='Successful local shared-regression directory')
    parser.add_argument('--tag', default='tpusoc_shared_20261105_v1')
    args = parser.parse_args()
    if not args.tag or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for c in args.tag):
        raise ValueError('Invalid package name')
    run = args.run.resolve()
    subprocess.run([sys.executable, str(ROOT / 'Server/Shared/Snapshot.py'), str(run), '--verify'], check=True)
    for name in ('ff1', 'one', 'twelve'):
        if 'PASS SHARED:' not in (run / (name + '.log')).read_text():
            raise ValueError('Local shared regression not complete: ' + name)
    for name in ('normal', 'zero', 'extreme', *(f'Layer{layer}' for layer in range(1, 12))):
        if 'PASS SHARED:' not in (run / ('ff1_' + name + '.log')).read_text():
            raise ValueError('Additional shared FF1 regression not complete: ' + name)
    out = ROOT / 'workspace/Server' / args.tag
    out.mkdir(parents=True, exist_ok=False)
    paths = ['Rtl', 'Sw', 'Backend/e203_subsys_nice_core.sv', 'Sim/SharedTest.sv',
             'Server/Shared', 'Server/Backend/SpFoundry.sv', 'Server/Backend/VerifyMacro.py',
             'Doc/SharedSram.md', 'Server/Results/20261105_Shared.md']
    for name in paths:
        source = ROOT / name
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        else:
            shutil.copy2(source, target)
    shutil.copytree(ROOT / 'workspace/Sim/out/Shared', out / 'Vectors')
    shutil.copy2(run / 'Firmware.hex', out / 'Firmware.hex')
    shutil.copy2(run / 'Shared.bin', out / 'Firmware.bin')
    shutil.copy2(run / 'SourceInputs.json', out / 'LocalSourceInputs.json')
    evidence = out / 'BuildEvidence'
    evidence.mkdir()
    for name in ('Shared.elf', 'Shared.map', 'Shared.ld', 'SharedLayout.h', 'SharedLayout.svh', 'Scope.json'):
        shutil.copy2(run / name, evidence / name)
    for path in out.rglob('*'):
        if path.is_file() and path.suffix == '.sh':
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
    metadata = {'scope': 'current worktree including uncommitted FF1/ICB; not frozen submission',
                'head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                'local_run': str(run), 'platform_sources': 'read from server, copied without datapath changes',
                'local_scope': json.loads((run / 'Scope.json').read_text())['scope']}
    (out / 'Bundle.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (out / 'MANIFEST.sha256').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(out).as_posix() + '\n'
        for p in sorted(out.rglob('*')) if p.is_file()))
    archive = out.with_name(out.name + '.tar.gz')
    with tarfile.open(archive, 'x:gz') as stream:
        for path in sorted(out.rglob('*')):
            if path.is_file():
                info = stream.gettarinfo(str(path), arcname=out.name + '/' + path.relative_to(out).as_posix())
                info.mode = 0o755 if path.suffix == '.sh' else 0o644
                with path.open('rb') as source:
                    stream.addfile(info, source)
    print(archive)
    print('BYTES', archive.stat().st_size)
    print('SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
