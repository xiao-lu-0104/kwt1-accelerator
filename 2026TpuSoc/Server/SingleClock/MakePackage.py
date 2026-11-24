"""Pinned source-only SMIC40 run bundle for the upstream single-clock top."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
COMMIT = '88e529eff28f4ba75fc250fe2e03310e267b3af7'
TAG = 'tpusoc_88e529e_single_asic_v1'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def verify_baseline():
    # Server tooling can live in later commits while the exported hardware is
    # pinned to the exact reviewed upstream revision. Never archive later RTL.
    if git(ROOT, 'diff', COMMIT, '--name-only', '--', 'Rtl', 'Backend', 'Sim', 'e203_hbirdv2').strip():
        raise ValueError('Hardware or simulator source differs from '+COMMIT)
    cpu = ROOT / 'e203_hbirdv2'
    if git(cpu, 'rev-parse', 'HEAD').decode().strip() != '9f3e34f337f5d0a1236a285871ffa2032491617a':
        raise ValueError('Unexpected E203 revision')
    if git(cpu, 'diff', 'HEAD', '--name-only').strip():
        raise ValueError('E203 tracked source has local changes')


def validate_tag(tag):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', tag):
        raise ValueError('Bundle tag must be a single directory name')
    return tag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default=TAG, help='New immutable artifact name')
    args = parser.parse_args()
    tag = validate_tag(args.tag)
    verify_baseline()
    parent = ROOT / 'workspace/Server'
    target = parent / tag
    parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)

    def write(name, data):
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def export(repo, prefix, paths, revision='HEAD'):
        with tarfile.open(fileobj=io.BytesIO(git(repo, 'archive', revision, *paths))) as stream:
            for entry in stream.getmembers():
                if entry.isfile():
                    write(prefix+entry.name, stream.extractfile(entry).read())

    export(ROOT, '', ('Rtl', 'Backend', 'Sim/Sram', 'Doc/Implementation.md', 'README.md'), COMMIT)
    cpu = ROOT / 'e203_hbirdv2'
    export(cpu, 'e203_hbirdv2/', ('rtl/e203/core', 'rtl/e203/general', 'LICENSE'))
    for name in ('SpFoundry.sv', 'SpBindingTest.sv', 'VerifyMacro.py', 'CompileSpLib.tcl', 'AsicCommon.tcl'):
        write('Server/Backend/'+name, (ROOT/'Server/Backend'/name).read_bytes().replace(b'\r\n', b'\n'))
    for name in ('Run.sh', 'Run.tcl', 'Constraints.tcl', 'Reports.tcl', 'README.md'):
        write('Server/SingleClock/'+name, (ROOT/'Server/SingleClock'/name).read_bytes().replace(b'\r\n', b'\n'))
    write('Server/Bundle.json', (json.dumps(dict(commit=COMMIT, top='E203TpuBackend',
          tools_checkout_commit=git(ROOT, 'rev-parse', 'HEAD').decode().strip(),
          clock='one shared 150MHz', macro='56 RAMSP1024X16', rtl_modified=False,
          previous_vendor_binding='server PASS at a1d0c9a; identical SRAM RTL',
          this_run_status='PENDING_SERVER_RUN'), indent=2)+'\n').encode())
    write('MANIFEST.sha256', ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(target).as_posix()+'\n'
          for p in sorted(target.rglob('*')) if p.is_file()).encode())
    archive = parent / (tag+'.tar.gz')
    with tarfile.open(archive, 'x:gz') as stream:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                info = stream.gettarinfo(str(path), arcname=path.relative_to(target).as_posix())
                info.mode = 0o755 if path.suffix == '.sh' else 0o644
                with path.open('rb') as source:
                    stream.addfile(info, source)
    print(archive)
    print('BYTES', archive.stat().st_size)
    print('SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
