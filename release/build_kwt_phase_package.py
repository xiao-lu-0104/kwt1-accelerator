import hashlib
from pathlib import Path
import tarfile
root=Path(__file__).resolve().parents[1]
tag='kwt_sram_phase_20261030_v8b'
destination=root/'release'/tag
destination.mkdir(exist_ok=True)
sources=list((root/'rtl').glob('*.v'))+list((root/'rtl').glob('*.vh'))
sources += [root/name for name in (
    'tb/tb_kwt_sram_phase.v','tb/tb_kwt_foundry_sram16.v','tb/tb_kwt_packed_sram.v','tb/tb_kwt_encoder_12.v',
    'tb/models/kwt_ramtp_contract.v','tools/run_kwt_sram_binding.sh',
    'syn/dc_compact.tcl','syn/compile_kwt_sram_libs.tcl','syn/kwt_encoder_12.sdc',
    'doc/SRAM半拍适配验证.md')]
sources+=list((root/'sim/vectors/enc12').glob('*'))
for source in sources:
    target=destination/source.relative_to(root)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(source.read_bytes().replace(b'\r\n',b'\n'))
(destination/'README.txt').write_text('''SPLIT-PHASE CANDIDATE 20261030_v8b
Bash 4.2 nounset compatibility fix: no empty timing-options array expansion.
A=root rising; captured B write=root falling. COLLDISN remains 1.
No foundry model or library is included. Server uses its original libraries.
Local contract tests passed; real macro simulation and fresh PPA are PENDING.
Old coedge PASS/checkpoints/area/timing cannot qualify this new RTL.

Full run (short timed test is FIRST and stops on a violation):
bash tools/run_kwt_sram_binding.sh --synth
Unit only:
bash tools/run_kwt_sram_binding.sh --suite unit

DC: 30 minute limit; original 1 ns setup/hold uncertainty retained.
No global hold optimization. Completion does not mean timing closure.
See doc/SRAM半拍适配验证.md for acceptance and reports.
''',encoding='utf-8',newline='\n')
evidence=destination/'local_evidence'
evidence.mkdir(exist_ok=True)
for name in ('phase_exact.log','phase_behavior.log','phase_tb_kwt_foundry_sram16.log','phase_tb_kwt_packed_sram.log'):
    (evidence/name).write_bytes((root/'release'/name).read_bytes().replace(b'\r\n',b'\n'))
(evidence/'STATUS.txt').write_text('LOCAL XSIM + TEST DOUBLE ONLY, NOT FOUNDRY QUALIFICATION\nTwo mutation controls (coedge, unstaged) were rejected.\nServer foundry tests and fresh synthesis PENDING.\n',newline='\n')
files=sorted(p for p in destination.rglob('*') if p.is_file() and p.name != 'MANIFEST.sha256')
(destination/'MANIFEST.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(destination).as_posix()+'\n' for p in files),encoding='utf-8',newline='\n')
archive=root/'release'/(tag+'.tar.gz')
with tarfile.open(archive,'w:gz') as stream:
    for source in sorted(destination.rglob('*')):
        if source.is_file(): stream.add(source,arcname=source.relative_to(destination).as_posix(),recursive=False)
print(archive)
print('BYTES',archive.stat().st_size)
print('SHA256',hashlib.sha256(archive.read_bytes()).hexdigest())
