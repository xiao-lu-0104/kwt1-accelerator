"""Package first SP controller/audit step; includes no vendor files or credentials."""
import argparse
import hashlib
from pathlib import Path
import re
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='kwt_sp_foundation_20261031_v1')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.tag):
        parser.error('Tag must be a simple filename')
    root = Path(__file__).resolve().parents[1]
    target = root / 'release' / args.tag
    archive = target.with_suffix('.tar.gz')
    if archive.exists():
        parser.error('Archive already exists; choose a new tag')
    target.mkdir(parents=True, exist_ok=False)
    names = [
        'rtl/kwt_sp_sram_ctrl.v', 'tb/models/kwt_sp_memory_model.v',
        'tb/tb_kwt_sp_sram_ctrl.v', 'tb/test_kwt_sp_foundation_tools.py',
        'tools/audit_kwt_sp_macro.py', 'tools/inspect_kwt_sram.py',
        'tools/inspect_kwt_sram_clock_arcs.py', 'tools/read_kwt_sram_datasheets.py',
        'tools/run_kwt_sp_foundation.sh', 'tools/make_sp_foundation_package.py',
        'doc/单端口存储改造.md', 'doc/架构重整规划_20261031.md',
        'doc/架构重整基线_20261031.json',
    ]
    for name in names:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((root / name).read_bytes().replace(b'\r\n', b'\n'))
    (target / 'README.txt').write_text('''REVISION: 20261031_sp_foundation_v1
RUN: bash tools/run_kwt_sp_foundation.sh
SCOPE: actual RAMSP1024X16 evidence + logical protocol test with a test double.
The existing encoder/CPU/half-phase implementation is NOT modified by this run.
No vendor model, proprietary library, converted datasheet or credential included.
No real macro binding is guessed; no DC, hold repair or full encoder is run.
Expected final status: FOUNDATION_REVIEW_READY, G1 OPEN, foundry timing NOT_RUN.
Return the terminal output (ports + datasheet excerpts + final summary).
Local XSIM four-config protocol test: PASS. Server VCS results are pending.
Protocol data widths/depths: 16x128, 32x1024, 16x4096, 128x128.
Source audit and datasheet extraction: <=120s each (+5s exit grace).
Protocol compilation: <=120s; simulation <=30s (+5s exit grace).
Every run creates a new directory under ~/soc; original shared files are read-only.
''', encoding='utf-8', newline='\n')
    evidence = target / 'local_evidence'
    evidence.mkdir()
    source = root / 'release/sp_ctrl_local_20261031/simulation.log'
    log = source.read_bytes().replace(b'\r\n', b'\n')
    if b'PASS: all SP controller protocol tests' not in log or b'Fatal:' in log:
        raise RuntimeError('Local protocol evidence is not PASS')
    (evidence / 'simulation.log').write_bytes(log)
    (evidence / 'STATUS.txt').write_text(
        'TEST DOUBLE ONLY. Not foundry timing or SRAM pin qualification.\n', encoding='ascii')
    files = sorted(p for p in target.rglob('*') if p.is_file())
    (target / 'MANIFEST.sha256').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(target).as_posix() + '\n'
        for p in files), encoding='utf-8', newline='\n')
    with tarfile.open(archive, 'x:gz') as stream:
        for p in sorted(target.rglob('*')):
            if p.is_file():
                stream.add(p, arcname=p.relative_to(target).as_posix(), recursive=False)
    print(archive)
    print('BYTES', archive.stat().st_size)
    print('SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
