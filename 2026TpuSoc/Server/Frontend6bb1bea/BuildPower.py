"""Package the current SysBus32 system and cold FF1/encoder activity flow."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import textwrap

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FRONT=ROOT/'2026TpuSoc_frontend_20261113_6bb1bea'
REV='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6'
CPU='9f3e34f337f5d0a1236a285871ffa2032491617a'
OUT=ROOT/'release/newpower_6bb1bea'

def sha(b):return hashlib.sha256(b).hexdigest()

def integration():
    original=(FRONT/'Backend/E203TpuBackend.sv').read_text()
    assert original==subprocess.check_output(['git','-C',str(FRONT),'show',REV+':Backend/E203TpuBackend.sv']).decode(), 'Backend content differs from frozen Git source'
    start=original.index('    TpuNice #(')
    end=original.index('    // CPU and DMA enter',start)
    connections={
        'Clock':'Clock','ResetN':'SystemResetN',
        'NiceRequestValid':'NiceRequestValid','NiceRequestReady':'NiceRequestReady',
        'NiceInst':'NiceInst','NiceRs1':'NiceRs1','NiceRs2':'NiceRs2',
        'NiceResponseValid':'NiceResponseValid','NiceResponseReady':'NiceResponseReady',
        'NiceResponseData':'NiceResponseData','NiceResponseError':'NiceResponseError',
        'NiceMemoryHold':'NiceMemoryHold','ComputeActive':'ComputeActive',
        'DmaActive':'DmaActive','LoaderActive':'LoaderActive',
        'SystemRequestValid':'DmaRequestValid','SystemRequestReady':'DmaRequestReady',
        'SystemRequestAddress':'DmaRequestAddress','SystemRequestReadEnable':'DmaRequestReadEnable',
        'SystemRequestWriteData':'DmaRequestWriteData','SystemRequestWriteMask':'DmaRequestWriteMask',
        'SystemResponseValid':'DmaResponseValid','SystemResponseReady':'DmaResponseReady',
        'SystemResponseData':'DmaResponseData','SystemResponseError':'DmaResponseError'}
    replacement='    SubmissionAccelerator Accelerator (\n'+',\n'.join('        .'+k+'('+v+')' for k,v in connections.items())+'\n    );\n'
    adapted=(original[:start]+replacement+original[end:]).replace('module E203TpuBackend #(', 'module FrozenBackend #(')
    (OUT/'integration/FrozenBackend.sv').write_text(adapted)
    (OUT/'integration/TpuResetSync.sv').write_bytes((FRONT/'Rtl/TpuResetSync.sv').read_bytes())
    head=original[:original.index(');')]
    ports=re.findall(r'\b(input|output)\s+logic\s*(\[[^\]]+\])?\s*(\w+)\s*[,\n]',head+'\n')
    assert len(ports)>50
    external=[(d,w,n) for d,w,n in ports if d=='output' or n in ('Clock','ResetN') or n.startswith('Flash')]
    internal=[(d,w,n) for d,w,n in ports if (d,w,n) not in external]
    top='module SystemPhysical (\n'+',\n'.join('    '+d+' logic '+w+' '+n for d,w,n in external)+'\n);\n'
    top+='\n'.join('    logic '+w+' '+n+';' for d,w,n in internal)+'\n'
    top+='    FrozenBackend #(.FastIcb(1),.DirectSystemBusDma(1)) Backend (.*);\n'
    top+='''
    logic ImReady, ImValid, FetchOwner, ItcmHalf;
    logic [63:0] ImData;
    logic FetchQueued,ItcmQueued,QueuedItcmRead;
    logic [15:0] QueuedFetchAddress,QueuedItcmAddress;
    logic [31:0] QueuedItcmData;
    logic [3:0] QueuedItcmMask;
    wire ChooseFetch=FetchQueued;
    wire ImRequestValid=(FetchQueued || ItcmQueued) && ImReady;
    // Independent one-entry queues: upstream LSU requires every destination
    // READY before issuing even an unrelated request. Never tie an idle ITCM
    // data READY low merely because the IFU currently owns the RAM port.
    assign FetchRequestReady=ResetN && !FetchQueued;
    assign ItcmRequestReady=ResetN && !ItcmQueued;
    assign FetchResponseValid=ImValid && FetchOwner;
    assign ItcmResponseValid=ImValid && !FetchOwner;
    assign FetchResponseData=ImData;
    assign ItcmResponseData=ItcmHalf ? ImData[63:32] : ImData[31:0];
    assign FetchResponseError=0;
    assign ItcmResponseError=0;
    assign DtcmResponseError=0;
    assign SystemResponseError=0;
    always_ff @(posedge Clock) begin
        if (!ResetN) begin
            FetchOwner<=0; ItcmHalf<=0; FetchQueued<=0;ItcmQueued<=0;
            QueuedFetchAddress<=0;QueuedItcmAddress<=0;QueuedItcmData<=0;QueuedItcmMask<=0;QueuedItcmRead<=1;
        end
        else begin
            if (FetchRequestValid && FetchRequestReady) begin FetchQueued<=1;QueuedFetchAddress<=FetchRequestAddress; end
            if (ItcmRequestValid && ItcmRequestReady) begin
                ItcmQueued<=1;QueuedItcmAddress<=ItcmRequestAddress;
                QueuedItcmData<=ItcmRequestWriteData;QueuedItcmMask<=ItcmRequestWriteMask;QueuedItcmRead<=ItcmRequestReadEnable;
            end
            if (ImReady && ImRequestValid) begin
                FetchOwner<=ChooseFetch;
                ItcmHalf<=QueuedItcmAddress[2];
                if (ChooseFetch) FetchQueued<=0;else ItcmQueued<=0;
            end
        end
    end
    PhysicalMemory #(.Bytes(65536),.DW(64)) Itcm (
        .Clock(Clock),.ResetN(ResetN),.RequestValid(ImRequestValid),
        .RequestReady(ImReady),.Address({16'b0,ChooseFetch ? QueuedFetchAddress : QueuedItcmAddress}),
        .ReadEnable(ChooseFetch || QueuedItcmRead),
        .WriteData({QueuedItcmData,QueuedItcmData}),
        .WriteMask(QueuedItcmAddress[2] ? {QueuedItcmMask,4'b0} : {4'b0,QueuedItcmMask}),
        .ResponseValid(ImValid),.ResponseReady(FetchOwner ? FetchResponseReady : ItcmResponseReady),.ResponseData(ImData)
    );
    PhysicalMemory #(.Bytes(65536),.DW(32)) Dtcm (
        .Clock(Clock),.ResetN(ResetN),.RequestValid(DtcmRequestValid),.RequestReady(DtcmRequestReady),
        .Address({16'b0,DtcmRequestAddress}),.ReadEnable(DtcmRequestReadEnable),
        .WriteData(DtcmRequestWriteData),.WriteMask(DtcmRequestWriteMask),
        .ResponseValid(DtcmResponseValid),.ResponseReady(DtcmResponseReady),.ResponseData(DtcmResponseData)
    );
    PhysicalMemory #(.Bytes(524288),.DW(32)) Shared (
        .Clock(Clock),.ResetN(ResetN),.RequestValid(SystemRequestValid),.RequestReady(SystemRequestReady),
        .Address(SystemRequestAddress),.ReadEnable(SystemRequestReadEnable),
        .WriteData(SystemRequestWriteData),.WriteMask(SystemRequestWriteMask),
        .ResponseValid(SystemResponseValid),.ResponseReady(SystemResponseReady),.ResponseData(SystemResponseData)
    );
endmodule
'''
    (OUT/'integration/SystemPhysical.sv').write_text(top)

def vectors():
    import numpy as np
    sys.path.insert(0,str(FRONT/'Model'))
    from Reference import Encoder, Quantize, QuantizeParameters
    model=ROOT/'2026TpuSoc/workspace/Model/official'
    raw=dict(np.load(model/'Layer0.npz'))
    params,fractions=QuantizeParameters(raw)
    input_value=Quantize(np.load(model/'Input0.npy'))
    values=Encoder(input_value,params,Fixed=True,Fractions=fractions)
    def binary(v):return np.asarray(v,dtype='<i2').tobytes()
    ff1=binary(values['Norm1'])+binary(np.concatenate([params['Ff1Weight'].T.reshape(-1),params['Ff1Bias']]))
    assert len(ff1)==45952
    (OUT/'vectors/ff1/source.bin').write_bytes(ff1)
    (OUT/'vectors/ff1/expected.bin').write_bytes(binary(values['Ff1']))
    image=bytearray(binary(input_value));addresses=[]
    for n in ['Query','Key','Value','Output','Norm1','Ff1','Ff2','Norm2']:
        addresses.append(0xa0000000+len(image))
        v=np.concatenate([params[n+'Gamma'],params[n+'Beta']]) if n.startswith('Norm') else params[n+'Weight'].T.reshape(-1)
        if not n.startswith('Norm') and n+'Bias' in params:v=np.concatenate([v,params[n+'Bias']])
        image.extend(binary(v))
    assert len(image)==112256
    (OUT/'vectors/encoder/source.bin').write_bytes(image)
    (OUT/'vectors/encoder/expected.bin').write_bytes(binary(values['Output']))
    names=['QueryWeight','KeyWeight','ValueWeight','OutputWeight','Norm1Gamma','Ff1Weight','Ff2Weight','Norm2Gamma']
    packed=sum((fractions[n]-1)<<(4*i) for i,n in enumerate(names))
    (OUT/'firmware/SocParams.h').write_text('static const TpuLayerParams SocLayerParams[12] = {\n    {'+', '.join(hex(a) for a in addresses+[packed])+'}\n};\n')
    (OUT/'firmware/Ff1Params.h').write_text('static const TpuFf1Params Ff1Params[12] = {\n    {0xa0000000, 0xa0003180, '+str(fractions['Ff1Weight'])+'}\n};\n')
    evidence={'frontend_commit':REV,'cpu_commit':CPU,'tasks':'one cold FF1 and one cold encoder layer; representative estimates, not twelve-task official evaluation',
              'model_inputs':{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in [model/'Input0.npy',model/'Layer0.npz']},
              'reference_source_sha256':sha((FRONT/'Model/Reference.py').read_bytes()),'matrix_rows':2,'source_prefetch':0,'cross_task_weight_prefetch':0}
    (OUT/'VectorEvidence.json').write_text(json.dumps(evidence,indent=2)+'\n')

def main():
    for name in ['integration','cpu','firmware','vectors/ff1','vectors/encoder','tools']:(OUT/name).mkdir(parents=True,exist_ok=True)
    assert subprocess.check_output(['git','-C',str(FRONT),'rev-parse','HEAD']).decode().strip()==REV
    integration();vectors()
    cpu=ROOT/'2026TpuSoc/e203_hbirdv2'
    assert subprocess.check_output(['git','-C',str(cpu),'rev-parse','HEAD']).decode().strip()==CPU
    wanted=[line.split('e203_hbirdv2/',1)[1] for line in (FRONT/'Backend/Files.f').read_text().splitlines() if line.startswith('e203_hbirdv2/')]
    includes='rtl/e203/core'
    data=subprocess.check_output(['git','-C',str(cpu),'archive',CPU]+wanted+[includes])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for m in archive:
            if m.isfile():
                p=OUT/'cpu'/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(m).read())
    for n in ['Start.S','BenchmarkMain.c','Encoder.c','Encoder.h','Tpu.h','Link.ld']:
        s=(FRONT/'Sw'/n).read_text()
        if n=='Start.S':
            s=s.replace('_start:\n','_start:\n    .option push\n    .option norvc\n'+''.join('    li x%d, 0\n'%r for r in range(1,32))+'    .option pop\n')
        (OUT/'firmware'/n).write_text(s)
    (OUT/'firmware/Build.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for task in ff1 encoder; do
  flags=()
  if [[ "$task" == ff1 ]]; then flags+=(-DBENCHMARK_FF1); fi
  riscv64-unknown-elf-gcc "${flags[@]}" -DTPU_BENCHMARK_PREFETCH -DTPU_FLAT_SHARED -march=rv32imac_zicsr -mabi=ilp32 -O2 -Wall -Wextra -Werror -ffreestanding -fno-builtin -msmall-data-limit=0 -nostdlib -I. -Wl,--build-id=none -Wl,-T,Link.ld Start.S BenchmarkMain.c Encoder.c -o "$task.elf"
  riscv64-unknown-elf-objcopy -O binary "$task.elf" "$task.bin"
done
''',newline='\n')
    if sys.platform=='win32':
        path='/mnt/e/chipdesign/release/newpower_6bb1bea/firmware/Build.sh'
        subprocess.check_call(['wsl','-d','ubuntu','--','env','PATH=/mnt/e/chipdesign/2026TpuSoc/workspace/HostTools:/usr/local/bin:/usr/bin:/bin','bash',path])
    else:subprocess.check_call(['bash',str(OUT/'firmware/Build.sh')])
    files={}
    for folder in ['integration','cpu','firmware','vectors']:
        for p in (OUT/folder).rglob('*'):
            if p.is_file():files[p.relative_to(OUT).as_posix()]=p.read_bytes()
    files['VectorEvidence.json']=(OUT/'VectorEvidence.json').read_bytes()
    for n in ['System.tcl','Power.tcl','PhysicalMemory.sv','PowerTest.sv','RunPower.py','NativeHelpers.py']:
        files['tools/'+n]=(HERE/n).read_bytes().replace(b'\r\n',b'\n')
    for n in ['AsicCommon.tcl','power_summary.py']:
        files['tools/'+n]=(HERE.parent/'Submission20261113'/n).read_bytes().replace(b'\r\n',b'\n')
    files['tools/Constraints.tcl']=(HERE/'Constraints.tcl').read_bytes().replace(b'\r\n',b'\n')
    files['PowerManifest.json']=(json.dumps({'source_commit':REV,'cpu_commit':CPU,
        'original_backend_sha256':sha(subprocess.check_output(['git','-C',str(FRONT),'show',REV+':Backend/E203TpuBackend.sv'])),
        'cpu_sources':wanted,'files_sha256':{n:sha(b) for n,b in sorted(files.items())}},indent=2)+'\n').encode()
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as archive:
        for n,b in sorted(files.items()):
            m=tarfile.TarInfo(n);m.mode=0o644;m.mtime=1794528000;m.size=len(b);archive.addfile(m,io.BytesIO(b))
    data=buf.getvalue();(OUT/'payload.tar.gz').write_bytes(data)
    shell='''#!/usr/bin/env bash
set -euo pipefail
umask 077
root="/tmp/final_power_6bb1bea_$(id -u)"
mkdir -p "$root"
if [[ ! -f "$root/PowerManifest.json" ]]; then
base64 -d > "$root/payload.tar.gz" <<'NEW_POWER_6BB1BEA'
'''+textwrap.fill(base64.b64encode(data).decode(),76)+'''
NEW_POWER_6BB1BEA
tar -xzf "$root/payload.tar.gz" -C "$root"
fi
exec > >(tee -a "$root/runner.log") 2>&1
echo "POWER_WORK_DIR=$root"
python3 -u "$root/tools/RunPower.py" "$root"
'''
    (OUT/'RunPower_6bb1bea.sh').write_text(shell,encoding='utf-8',newline='\n')
    (OUT/'Build.json').write_text(json.dumps({'source_commit':REV,'files':len(files),'payload_bytes':len(data),'script_chars':len(shell)},indent=2)+'\n')
    print((OUT/'Build.json').read_text())

if __name__=='__main__':main()
