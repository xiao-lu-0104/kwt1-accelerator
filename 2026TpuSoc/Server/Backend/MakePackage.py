"""Export a small, source-only backend bundle of the current pinned revision."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
COMMIT = 'a1d0c9aa5f6f549b2f637f96be6a6e5ed305ce00'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='tpusoc_a1d0c9a_asic_20261102_v3d')
    args = parser.parse_args()
    if not args.tag.replace('_', '').replace('-', '').isalnum():
        parser.error('Tag must be a simple filename')
    if git(ROOT, 'rev-parse', 'HEAD').decode().strip() != COMMIT:
        raise ValueError('Unexpected project revision')
    if git(ROOT, 'diff', 'HEAD', '--name-only').strip():
        raise ValueError('Tracked source changed; review before packaging')
    parent = ROOT / 'workspace/Server'
    parent.mkdir(parents=True, exist_ok=True)
    tag = args.tag
    target = parent / tag
    target.mkdir(exist_ok=False)

    def write(name, data):
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def export(repo, prefix, paths):
        with tarfile.open(fileobj=io.BytesIO(git(repo, 'archive', 'HEAD', *paths))) as stream:
            for member in stream.getmembers():
                if member.isfile():
                    write(prefix + member.name, stream.extractfile(member).read())

    export(ROOT, '', ('Rtl', 'Sim/CdcTest.sv', 'Sim/Sram', 'Fpga', 'Doc/Cdc.md'))
    cpu = ROOT / 'e203_hbirdv2'
    export(cpu, 'e203_hbirdv2/', ('rtl/e203/core', 'rtl/e203/general', 'LICENSE'))
    for path in sorted((ROOT / 'Server/Backend').iterdir()):
        if path.is_file():
            write('Server/Backend/' + path.name, path.read_bytes().replace(b'\r\n', b'\n'))
    metadata = dict(commit=COMMIT, cpu_commit=git(cpu, 'rev-parse', 'HEAD').decode().strip(),
                    purpose='SMIC40 TT ASIC synthesis: reviewed real SP macro binding candidate, TPU and CPU+TPU',
                    foundry_sram='BINDING_CANDIDATE_PENDING_VENDOR_VALIDATION',
                    asic_synthesis='NOT_RUN', server_status='PENDING')
    write('Server/Backend/Bundle.json', (json.dumps(metadata, indent=2) + '\n').encode())
    write('MANIFEST.sha256', ''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' +
          p.relative_to(target).as_posix() + '\n' for p in sorted(target.rglob('*')) if p.is_file()).encode())
    archive = parent / (tag + '.tar.gz')
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
