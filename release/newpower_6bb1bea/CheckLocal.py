"""WSL-only integration smoke: real CPU/RTL, explicitly local RAM test doubles."""
import json
from pathlib import Path
import subprocess
import sys
import os

ROOT=Path('/mnt/e/chipdesign')
OUT=ROOT/'release/newpower_6bb1bea'
TOOLS=ROOT/'2026TpuSoc/Server/Frontend6bb1bea'
FRONT=ROOT/'2026TpuSoc_frontend_20261113_6bb1bea'
directory=OUT/'local_check';directory.mkdir(exist_ok=True)
fixture=(ROOT/'2026TpuSoc/Server/Backend/LocalRamspFixture.sv').read_text()
fixture=fixture.replace('    logic [15:0] Words [1024];','    logic [15:0] Words [1024];\n    initial foreach(Words[i]) Words[i]=0;')
fixture+='''
module RAMSP4096X16(output logic [15:0] Q,input logic CLK,CEN,GWEN,
    input logic [15:0] WEN,input logic [11:0] A,input logic [15:0] D,
    input logic [2:0] EMA,input logic [1:0] EMAW,input logic RET1N);
    logic [15:0] Words[4096];
    initial foreach(Words[i]) Words[i]=0;
    always @(posedge CLK) if(!CEN) begin
        if(!GWEN) begin for(int b=0;b<16;b++) if(!WEN[b]) Words[A][b]<=D[b]; end
        else Q<=Words[A];
    end
endmodule
'''
(directory/'LocalRamModels.sv').write_text(fixture)
init=['module MemoryInit;','bit Done=0;','string Prefix;','initial begin','#0.1;',
      'if (!$value$plusargs("INIT_PREFIX=%s",Prefix)) $fatal(1,"No init prefix");']
for bank in range(2):
    for lane in range(4):
        init.append('$readmemh({Prefix,"/itcm_%d_%d.hex"},PowerTest.Dut.Itcm.BanksLoop[%d].Lanes[%d].Macro.Words);'%(bank,lane,bank,lane))
init+=['Done=1;','end','endmodule']
if os.environ.get('PIN_INIT_CHECK')=='1':
    sys.path[:0]=[str(TOOLS),str(ROOT/'2026TpuSoc/Server/Submission20261113')]
    import RunPower
    RunPower.sv_path=lambda value:value.replace('/','.')
    cells={}
    for r in range(7):
        for l in range(8):cells['Backend/Accelerator/Tpu/Core/Sram/Storage[%d]/Banks[%d]/Memory/Macro'%(r,l)]='RAMSP1024X16'
    for region,banks,lanes in [('Itcm',2,4),('Dtcm',4,2),('Shared',32,2)]:
        for b in range(banks):
            for l in range(lanes):cells[region+'/BanksLoop[%d]/Lanes[%d]/Macro'%(b,l)]='RAMSP4096X16'
    generated=RunPower.initialize(OUT,'ff1',cells,[])/'MemoryInit.sv'
    pintext=generated.read_text()
    pintext=pintext.replace('integer Word;','integer Word;\nstring Prefix;')
    pintext=pintext.replace('initial begin','initial begin\nif (!$value$plusargs("INIT_PREFIX=%s",Prefix)) $fatal(1,"No init prefix");',1)
    pintext=__import__('re').sub(r'\$readmemh\("[^"\n]*/(firmware32\.hex)"',lambda m:'$readmemh({Prefix,"/'+m[1]+'"}',pintext)
    (directory/'MemoryInit.sv').write_text(pintext)
else:
    (directory/'MemoryInit.sv').write_text('\n'.join(init)+'\n')
manifest=json.loads((OUT/'PowerManifest.json').read_text()) if (OUT/'PowerManifest.json').exists() else None
# BuildPower packages the manifest inside payload; CPU file order matches upstream.
cpu=[OUT/'cpu'/line[len('e203_hbirdv2/'):] for line in (FRONT/'Backend/Files.f').read_text().splitlines() if line.startswith('e203_hbirdv2/')]
names='TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer TpuMatmul TpuGelu TpuVector TpuDma TpuLocalCopy TpuFf1Stream TpuIcb TpuTop TpuNice'.split()
sources=[FRONT/'Rtl'/(n+'.sv') for n in names]+[ROOT/'2026TpuSoc/Server/Backend/SpFoundry.sv',TOOLS/'SubmissionAccelerator.sv']+cpu
sources += [OUT/'integration/TpuResetSync.sv',OUT/'integration/FrozenBackend.sv',TOOLS/'PhysicalMemory.sv',OUT/'integration/SystemPhysical.sv',
            TOOLS/'PowerTest.sv',directory/'MemoryInit.sv',directory/'LocalRamModels.sv']
args=['verilator','--binary','--timing','--assert','--build','-j','4','-Wno-fatal','-Wno-PINMISSING','-Wno-UNUSEDSIGNAL','-Wno-UNUSEDPARAM',
      '-Wno-DECLFILENAME','-Wno-TIMESCALEMOD','--top-module','PowerTest','+define+TPU_SRAM_MODEL','+define+TPU_MATRIX_ROWS=2','+define+LOCAL_POWER_TEST',
      '+incdir+'+str(OUT/'cpu/rtl/e203/core'),'--Mdir',str(directory/'build')]
args += [str(FRONT/'Sim/E203.vlt'),str(ROOT/'2026TpuSoc/Server/Backend/LocalReset.vlt')]+[str(p) for p in sources]
if not (directory/'build/VPowerTest').is_file() or (directory/'build/VPowerTest').stat().st_mtime < max(p.stat().st_mtime for p in sources):
    with (directory/'Build.log').open('w') as f:
        p=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT)
    if p.returncode:
        print((directory/'Build.log').read_text()[-12000:]);sys.exit(p.returncode)
for task in ['ff1','encoder']:
    dest=directory/task;dest.mkdir(exist_ok=True)
    fw=(OUT/'firmware'/(task+'.bin')).read_bytes();fw+=bytes(65536-len(fw))
    (dest/'firmware32.hex').write_text(''.join('%08x\n'%int.from_bytes(fw[i:i+4],'little') for i in range(0,len(fw),4)))
    for bank in range(2):
        for lane in range(4):
            (dest/('itcm_%d_%d.hex'%(bank,lane))).write_text(''.join('%04x\n'%int.from_bytes(fw[bank*32768+i*8+lane*2:bank*32768+i*8+lane*2+2],'little') for i in range(4096)))
    for n in ['source','expected']:
        b=(OUT/'vectors'/task/(n+'.bin')).read_bytes()
        (dest/(n+'.hex')).write_text(''.join('%08x\n'%int.from_bytes(b[i:i+4],'little') for i in range(0,len(b),4)))
    with (dest/'Run.log').open('w') as f:
        p=subprocess.run([str(directory/'build/VPowerTest'),'+TASK='+task,'+SOURCE='+str(dest/'source.hex'),'+EXPECTED='+str(dest/'expected.hex'),
                          '+SAIF='+str(dest/'unused.saif'),'+INIT_PREFIX='+str(dest)],cwd=dest,stdout=f,stderr=subprocess.STDOUT)
    print(task, 'EXIT',p.returncode,flush=True);print((dest/'Run.log').read_text()[-3000:],flush=True)
    if p.returncode:sys.exit(p.returncode)
print('LOCAL_NEW_SYSTEM_COLD_TASKS_PASS; local models, no measured power')
