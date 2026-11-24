"""Build the isolated v11 server regression package without vendor files."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tarfile


def main():
    root = Path(__file__).resolve().parents[1]
    tag = 'kwt_encoder_mmio_20261030'
    target = root / 'release' / tag
    # Exclusive destination avoids silently mixing source revisions.
    target.mkdir(parents=True, exist_ok=False)
    names = (
        'README.md', 'doc/MMIO接口.md', 'doc/SoC参数接口接入.md',
        'sw/kwt_encoder.c', 'sw/kwt_encoder.h', 'tb/test_kwt_driver.c',
        'tb/tb_kwt_sram_phase.v', 'tb/tb_kwt_foundry_sram16.v',
        'tb/tb_kwt_packed_sram.v', 'tb/tb_kwt_encoder_12.v',
        'tb/tb_kwt_param_stream.v', 'tb/tb_kwt_encoder_param_load.v',
        'tb/tb_kwt_encoder_mmio.v', 'tb/tb_kwt_encoder_axi.v',
        'tb/models/kwt_ramtp_contract.v',
        'tools/run_kwt_sram_binding.sh', 'tools/pack_kwt_param_stream.py',
        'tools/make_encoder_mmio_package.py',
        'syn/dc_compact.tcl', 'syn/compile_kwt_sram_libs.tcl',
        'syn/kwt_encoder_12.sdc',
    )
    sources = [root / name for name in names]
    sources += list((root / 'rtl').glob('*.v')) + list((root / 'rtl').glob('*.vh'))
    sources += [p for p in (root / 'sim/vectors/enc12').glob('*')
                if p.is_file() and not p.name.startswith('param_stream.')]
    for source in sources:
        dest = target / source.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Only text files are normalized; binary parameter payload is generated
        # below and must never pass through CRLF replacement.
        dest.write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
    subprocess.run([sys.executable, str(root / 'tools/pack_kwt_param_stream.py'),
                    '--vectors', str(root / 'sim/vectors/enc12'),
                    '--out', str(target / 'sim/vectors/enc12')], check=True)
    (target / 'README.txt').write_text('''REVISION: 20261030_v11_encoder_mmio
AXI peripheral task: input, 32-bit parameter stream, control and output SRAM.
RUN: bash tools/run_kwt_sram_binding.sh --encoder-mmio
Three tests: specify-enabled SRAM phase; MMIO protocol; full encoder over AXI.
Local short protocol and host C driver tests PASS. The server full AXI golden
regression is PENDING. A bus-functional master is used, NOT an E203 CPU.
The prior v10 real-macro seven-test parameter regression passed on the server.
No synthesis/hold repair runs here. --encoder-mmio --synth is rejected because
the existing DC script still targets the standalone 40-macro core.
The peripheral is expected to use 44 RAMTP1024X16 / 88 KiB; new PPA is PENDING.
Frozen v8b/v9 PPA cannot qualify this new top. Original 1ns hold remains open.
No vendor model, library or checkpoint is included; models are copied from the
original server library to a new run. See doc/MMIO接口.md for scope and protocol.
''', encoding='utf-8', newline='\n')
    evidence = target / 'local_evidence'
    evidence.mkdir()
    log = root / 'release/mmio_protocol.log'
    if log.exists():
        content = log.read_bytes()
        if b'PASS: encoder MMIO channel ordering' not in content or b'Fatal:' in content:
            raise RuntimeError('Local protocol log is not a PASS')
        (evidence / log.name).write_bytes(content.replace(b'\r\n', b'\n'))
    (evidence / 'STATUS.txt').write_text('''LOCAL TEST SCOPE
XSIM protocol test uses synthetic core events + explicit SRAM test double.
Host C driver test uses an emulated register device, no CPU instructions.
Full real-macro AXI regression, E203 execution and new top PPA are pending.
''', encoding='utf-8', newline='\n')
    files = sorted(p for p in target.rglob('*') if p.is_file())
    (target / 'MANIFEST.sha256').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' +
        p.relative_to(target).as_posix() + '\n' for p in files),
        encoding='utf-8', newline='\n')
    archive = root / 'release' / (tag + '.tar.gz')
    with tarfile.open(archive, 'x:gz') as stream:
        for p in sorted(target.rglob('*')):
            if p.is_file():
                stream.add(p, arcname=p.relative_to(target).as_posix(), recursive=False)
    print(archive)
    print('BYTES', archive.stat().st_size)
    print('SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
