"""Package the v12 E203 C-driver candidate, prebuilt images and original checks."""
from pathlib import Path
import argparse
import hashlib
import json
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',type=Path,required=True)
    parser.add_argument('--smoke',type=Path,required=True)
    args=parser.parse_args()
    tag='kwt_e203_c_driver_20261030'
    target=ROOT/'release'/tag
    target.mkdir(parents=True,exist_ok=False)
    sources=list((ROOT/'rtl').glob('*.v'))+list((ROOT/'rtl').glob('*.vh'))
    sources += [ROOT/name for name in (
        'README.md','doc/E203编码器集成.md','doc/MMIO接口.md','doc/SoC参数接口接入.md',
        'tools/run_e203_kwt.sh','tools/prepare_e203_kwt.py','tools/build_e203_kwt_images.py',
        'tools/make_e203_kwt_package.py','tools/pack_kwt_param_stream.py',
        'tb/tb_kwt_e203.v','tb/models/kwt_ramtp_contract.v','tb/test_e203_kwt_tools.py',
        'tb/test_kwt_driver.c','sw/kwt_encoder.c','sw/kwt_encoder.h')]
    sources += list((ROOT/'sw/e203').glob('*'))
    sources += [p for p in (ROOT/'sim/vectors/enc12').glob('*') if p.is_file()]
    for source in sources:
        dest=target/source.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(source.read_bytes().replace(b'\r\n',b'\n'))
    for kind,directory in (('full',args.full),('smoke',args.smoke)):
        record=json.loads((directory/'build.json').read_text(encoding='utf-8'))
        if record['smoke']!=(kind=='smoke'):
            raise ValueError('Wrong image build mode '+kind)
        for relative,expected in record['source_sha256'].items():
            actual=hashlib.sha256((ROOT/relative).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            if actual!=expected:raise ValueError('Image does not match current source '+relative)
        dest=target/'images'/kind
        dest.mkdir(parents=True)
        for filename,expected in record['files'].items():
            if digest(directory/filename)!=expected:raise ValueError('Image checksum mismatch '+filename)
            (dest/filename).write_bytes((directory/filename).read_bytes())
        (dest/'build.json').write_bytes((directory/'build.json').read_bytes())
    evidence=target/'local_evidence'
    evidence.mkdir()
    local_log=ROOT/'release/e203_kwt_soc_smoke.log'
    content=local_log.read_bytes()
    if b'PASS: E203 CPU boot' not in content or b'Fatal:' in content:
        raise ValueError('Local CPU smoke has not passed')
    (evidence/local_log.name).write_bytes(content.replace(b'\r\n',b'\n'))
    (evidence/'XSIM_COMPATIBILITY.txt').write_bytes((ROOT/'release/e203_xchecker_compatibility.txt').read_bytes())
    (evidence/'STATUS.txt').write_text('''LOCAL DIAGNOSTIC ONLY
XSIM reference SoC + explicit accelerator SRAM test double.
Local config capacity matches server (256KiB each); top header included for XSIM.
Concurrent X checker was replaced by same-predicate event check in LOCAL COPY.
Original concurrent assertions stay UNMODIFIED in the server runner/platform.
Local smoke passes; server smoke and full CPU golden regression are PENDING.
''',encoding='utf-8',newline='\n')
    compiler=target/'toolchain'
    compiler.mkdir()
    (compiler/'source.json').write_bytes((ROOT/'external/toolchains/zig-wheel-source.json').read_bytes())
    (target/'README.txt').write_text('''REVISION: 20261030_v12_e203_c_driver
RUN: bash tools/run_e203_kwt.sh
Original competition e203_soc_top + real CPU C program + ICB/AXI + real encoder.
Short CPU/MMIO test first, then full 6336-byte DTCM output comparison.
All model/input movement and final output stores are performed by the CPU.
Program/model/input are initially preloaded into existing TCMs (simulation).
Prebuilt RV32 C ELFs and source hashes included; no server cross compiler needed.
Local diagnostic smoke passed with XSIM-specific checker compatibility, explicitly
documented. Server keeps ALL ORIGINAL CPU ASSERTIONS; actual VCS results pending.
No synthesis, global hold repair, vendor libraries, platform RTL or old checkpoint.
PPA/signoff remain pending; do not substitute CPU simulation for timing closure.
''',encoding='utf-8',newline='\n')
    files=sorted(p for p in target.rglob('*') if p.is_file())
    (target/'MANIFEST.sha256').write_text(''.join(digest(p)+'  '+p.relative_to(target).as_posix()+'\n' for p in files),encoding='utf-8',newline='\n')
    archive=target.with_suffix('.tar.gz')
    with tarfile.open(archive,'x:gz') as stream:
        for p in sorted(target.rglob('*')):
            if p.is_file():stream.add(p,arcname=p.relative_to(target).as_posix(),recursive=False)
    print(archive)
    print('BYTES',archive.stat().st_size)
    print('SHA256',digest(archive))


if __name__=='__main__':
    main()
