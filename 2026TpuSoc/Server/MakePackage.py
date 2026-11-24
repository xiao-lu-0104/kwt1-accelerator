"""Bundle the pinned new repository and its tested static Linux RTL simulations."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'a671d5da433c6ae2ac1479c5bfba2434f6631414'
CPU = '9f3e34f337f5d0a1236a285871ffa2032491617a'
MODEL = '237e4097afd4f6851e0b82f0a8d65c2dfe8eae30'


def git(directory, *args):
    return subprocess.check_output(['git', '-C', str(directory), *args])


def write(target, name, data):
    dest = target / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def export(target, directory, prefix='', paths=()):
    content = git(directory, 'archive', '--format=tar', 'HEAD', *paths)
    with tarfile.open(fileobj=io.BytesIO(content)) as stream:
        for member in stream.getmembers():
            if member.isfile():
                write(target, prefix + member.name, stream.extractfile(member).read())


def static_elf(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 62:
        raise ValueError('Not x86-64 ELF: ' + str(path))
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if not count or any(struct.unpack_from('<I', data, offset + i * size)[0] == 3 for i in range(count)):
        raise ValueError('Not statically linked: ' + str(path))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='tpusoc_a671d5d_20261101_v1')
    args = parser.parse_args()
    if not args.tag.replace('_', '').replace('-', '').isalnum():
        parser.error('Tag must be a simple filename')
    for repo, expected in [(ROOT, COMMIT), (ROOT / 'e203_hbirdv2', CPU), (ROOT / 'keyword-transformer', MODEL)]:
        if git(repo, 'rev-parse', 'HEAD').decode().strip() != expected:
            raise ValueError('Pinned source revision mismatch: ' + str(repo))
        if git(repo, 'diff', '--name-only').strip():
            raise ValueError('Tracked original source modified: ' + str(repo))
    for name, marker in [('LocalTest.log', 'PASS GELU:'), ('LocalSoc.log', 'PASS E203 + TPU: layers 12,'),
                         ('LocalOfficial.log', 'PASS: all 12 parameter sets also tested')]:
        text = (ROOT / 'workspace/Checks' / name).read_text()
        if marker not in text or 'FAIL:' in text or 'Error-' in text:
            raise ValueError('Missing/failed local evidence: ' + name)
    parent = ROOT / 'workspace/Server'
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / args.tag
    archive = parent / (args.tag + '.tar.gz')
    if archive.exists():
        parser.error('Archive already exists')
    target.mkdir(exist_ok=False)
    export(target, ROOT)
    export(target, ROOT / 'e203_hbirdv2', 'e203_hbirdv2/', ('rtl/e203/core', 'rtl/e203/general', 'LICENSE'))
    for name in ['LICENSE.txt', 'models_data_v2_12_labels/kwt1/best_weights.index',
                 'models_data_v2_12_labels/kwt1/best_weights.data-00000-of-00001',
                 'models_data_v2_12_labels/kwt1/flags.json', 'models_data_v2_12_labels/kwt1/labels.txt']:
        write(target, 'keyword-transformer/' + name, git(ROOT / 'keyword-transformer', 'show', 'HEAD:' + name))
    for path in sorted((ROOT / 'Server').glob('*')):
        if path.is_file():
            write(target, 'Server/' + path.name, path.read_bytes().replace(b'\r\n', b'\n'))
    executables = [
        'workspace/Sim/build/VTpuTop', 'workspace/Sim/build/arithmetic/VArithmeticTest',
        'workspace/Sim/build/nice/VNiceTest', 'workspace/Sim/build/axi/VTpuAxi',
        'workspace/Sim/build/gelu/VTpuGelu', 'workspace/Sim/build/soc/VE203Tpu',
    ]
    for name in executables:
        write(target, 'Server/Bin/' + Path(name).name, static_elf(ROOT / name))
    for group in ['synthetic', 'zero', 'extreme'] + ['official%d' % i for i in range(12)]:
        for path in (ROOT / 'workspace/Sim/out' / group).iterdir():
            if path.suffix == '.bin' or path.name in ('Program.txt', 'ProgramRun.txt'):
                data = path.read_bytes()
                if path.suffix == '.txt':
                    data = data.replace(b'/mnt/e/chipdesign/2026TpuSoc/', b'')
                    if b'/mnt/' in data or b'E:/' in data:
                        raise ValueError('Unrelocated program path: ' + str(path))
                write(target, path.relative_to(ROOT).as_posix(), data)
    for pattern in ['Expected*.bin', 'Ddr.bin', 'Head.npz', 'Reference.json']:
        for path in (ROOT / 'workspace/Sim/out/Soc').glob(pattern):
            write(target, path.relative_to(ROOT).as_posix(), path.read_bytes())
    for name in ['workspace/Sw/Soc.bin', 'workspace/Sw/Soc.elf', 'workspace/Sw/Soc.dump',
                 'workspace/Sw/Soc.map', 'workspace/Sw/SocParams.h', 'workspace/Sim/out/GeluExpected.bin',
                 'workspace/Model/official/Manifest.json']:
        write(target, name, (ROOT / name).read_bytes())
    for path in (ROOT / 'workspace/Model/official').glob('*.np*'):
        write(target, path.relative_to(ROOT).as_posix(), path.read_bytes())
    for name in ['LocalTest.log', 'LocalSoc.log', 'LocalOfficial.log']:
        write(target, 'Server/LocalEvidence/' + name, (ROOT / 'workspace/Checks' / name).read_bytes())
    metadata = dict(repository='https://github.com/kkk73/2026TpuSoc', commit=COMMIT,
                    cpu_commit=CPU, model_commit=MODEL, numpy='2.5.4',
                    verilator='5.050 2026-07-01 rev v5.050-60-g3d2421f3b', host_compiler='GCC 13.3.0',
                    rtl_and_original_tests_modified=False, original_assertions_enabled=True,
                    executables='static Linux x86-64, no Verilator runtime/compiler needed on server',
                    firmware_toolchain='riscv64-linux-gnu GCC, freestanding RV32IMAC_Zicsr',
                    firmware_extra_flags=['-fno-pie', '-no-pie'],
                    local_status='test, official, soc PASS', server_status='PENDING',
                    foundry_sram='NOT_BOUND', asic_synthesis='NOT_RUN')
    write(target, 'Server/Bundle.json', (json.dumps(metadata, indent=2) + '\n').encode())
    files = sorted(p for p in target.rglob('*') if p.is_file())
    write(target, 'MANIFEST.sha256', ''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(target).as_posix() + '\n'
        for p in files).encode())
    with tarfile.open(archive, 'x:gz') as stream:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                info = stream.gettarinfo(str(path), arcname=path.relative_to(target).as_posix())
                info.mode = 0o755 if 'Server/Bin/' in info.name or path.suffix == '.sh' else 0o644
                with path.open('rb') as source:
                    stream.addfile(info, source)
    print(archive)
    print('FILES', len(files) + 1)
    print('BYTES', archive.stat().st_size)
    print('SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
