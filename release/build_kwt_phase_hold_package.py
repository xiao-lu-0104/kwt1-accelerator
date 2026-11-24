from pathlib import Path
import hashlib,tarfile
root=Path(__file__).resolve().parents[1]
tag='kwt_phase_hold_pilot_20261030'
target=root/'release'/tag
target.mkdir(exist_ok=True)
for name in ('tools/rerun_kwt_sram_synthesis.sh','syn/dc_compact.tcl','syn/audit_kwt_hold.tcl',
             'syn/kwt_encoder_12.sdc','tools/inspect_kwt_sram_clock_arcs.py',
             'doc/SRAM半拍保持时间试验.md'):
    dest=target/name
    dest.parent.mkdir(exist_ok=True,parents=True)
    dest.write_bytes((root/name).read_bytes().replace(b'\r\n',b'\n'))
(target/'README.txt').write_text('''REVISION: 20261030_v9_phase_hold_pilot
Use ONLY the verified split-phase run from 20261030_161124.
This package includes no RTL, foundry models, libraries or old netlists.
It reuses the four passing foundry-model tests, existing SRAM DBs and original
compiled checkpoint. Inputs and checkpoint are checked for changes.

Command:
bash tools/rerun_kwt_sram_synthesis.sh --run-dir ~/soc/kwt_sram_20261030_161124_* --phase-pilot 0.10

20-minute optimization limit, plus 30 seconds exit grace.
Explicit 100 ps hold uncertainty TRIAL; setup stays 1 ns, IO unchanged.
The original 1 ns hold baseline remains FAIL. This is not final-budget acceptance.
All original timing arcs are kept. Area/setup/hold and all four phase-path checks
must pass for the pilot to pass. See the resulting summary.txt and dc_out_bound.
''',encoding='utf-8',newline='\n')
files=sorted(p for p in target.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256')
(target/'MANIFEST.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(target).as_posix()+'\n' for p in files),encoding='utf-8',newline='\n')
archive=root/'release'/(tag+'.tar.gz')
with tarfile.open(archive,'w:gz') as stream:
    for p in sorted(target.rglob('*')):
        if p.is_file(): stream.add(p,arcname=p.relative_to(target).as_posix(),recursive=False)
print(archive)
print('BYTES',archive.stat().st_size)
print('SHA256',hashlib.sha256(archive.read_bytes()).hexdigest())
