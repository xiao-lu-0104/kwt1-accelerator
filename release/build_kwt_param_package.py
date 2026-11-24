from pathlib import Path
import hashlib,tarfile,subprocess,sys
root=Path(__file__).resolve().parents[1]
tag='kwt_param_handshake_20261030'
target=root/'release'/tag
target.mkdir(exist_ok=True)
sources=list((root/'rtl').glob('*.v'))+list((root/'rtl').glob('*.vh'))
sources += [root/name for name in (
    'tb/tb_kwt_sram_phase.v','tb/tb_kwt_foundry_sram16.v','tb/tb_kwt_packed_sram.v',
    'tb/tb_kwt_encoder_12.v','tb/tb_kwt_param_stream.v','tb/tb_kwt_encoder_param_load.v',
    'tb/models/kwt_ramtp_contract.v','tools/run_kwt_sram_binding.sh','tools/pack_kwt_param_stream.py',
    'syn/dc_compact.tcl','syn/compile_kwt_sram_libs.tcl','syn/kwt_encoder_12.sdc',
    'doc/SoC参数接口接入.md')]
sources += [p for p in (root/'sim/vectors/enc12').glob('*') if p.is_file()]
for source in sources:
    dest=target/source.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(source.read_bytes().replace(b'\r\n',b'\n'))
packed=target/'sim/vectors/enc12'
if not (packed/'param_stream.mem').exists():
    subprocess.run([sys.executable,str(root/'tools/pack_kwt_param_stream.py'),'--vectors',str(root/'sim/vectors/enc12'),'--out',str(packed)],check=True)
(target/'README.txt').write_text('''REVISION: 20261030_v10_parameter_handshake
Integration preparation: parameter valid/ready and 32-to-64-bit stream.
FFN length truncation fixed: each block loads once, 3782 records per layer.
Local short tests pass. Full real-macro default/stream golden regressions PENDING.
No CPU/AXI integration PASS is claimed; this is its first prerequisite.
Frozen v8b/v9 SRAM PPA and checkpoints do not qualify this changed RTL.

RUN (seven tests, no synthesis/hold repair):
bash tools/run_kwt_sram_binding.sh --param-handshake

Expected default: 6336 values bit-exact, 3159181 cycles.
Expected streamed: 6336 values bit-exact, 45384 records/90768 words, cycles equal
3159181 plus observed parameter wait cycles. Invalid parameter payload is X.
The parameter stream is little endian: low 32-bit word, then high word.
This package includes no foundry model/library/netlist; original server models
are copied into a new run. All original specify/collision checks are kept in
the pin-level phase test; ideal RTL full compute uses +notimingcheck.
See doc/SoC参数接口接入.md for current scope and next integration steps.
''',encoding='utf-8',newline='\n')
evidence=target/'local_evidence';evidence.mkdir(exist_ok=True)
for name in ('tb_kwt_param_stream.log','tb_kwt_encoder_param_load.log'):
    (evidence/name).write_bytes((root/'release'/name).read_bytes().replace(b'\r\n',b'\n'))
(evidence/'STATUS.txt').write_text('LOCAL XSIM + EXPLICIT SRAM TEST DOUBLE ONLY\nParameter-load contract, stream backpressure/reset pass.\nMutation controls reject old length truncation and ignored valid.\nFull server golden compute and new PPA PENDING; no CPU test yet.\n',newline='\n')
files=sorted(p for p in target.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256')
(target/'MANIFEST.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(target).as_posix()+'\n' for p in files),encoding='utf-8',newline='\n')
archive=root/'release'/(tag+'.tar.gz')
with tarfile.open(archive,'w:gz') as stream:
    for p in sorted(target.rglob('*')):
        if p.is_file():stream.add(p,arcname=p.relative_to(target).as_posix(),recursive=False)
print(archive)
print('BYTES',archive.stat().st_size)
print('SHA256',hashlib.sha256(archive.read_bytes()).hexdigest())
