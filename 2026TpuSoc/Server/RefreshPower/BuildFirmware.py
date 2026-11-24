"""Stage current upstream driver plus the unchanged shared-TCM harness and boot GPR initialization."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FRONT=ROOT.parent/'2026TpuSoc_frontend_20261109'
REV='c03eb048481b7d271dba54e518092c2eb9aa528f'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def adapt_main(text):
    old='TpuRunFf1(TPU_INPUT, TPU_PARAMETERS, TPU_OUTPUT, Mail[6])'
    if text.count(old)!=1: raise ValueError('Unexpected original FF1 invocation')
    return text.replace(old,'TpuRunFf1(TPU_INPUT, TPU_PARAMETERS, Mail[6], TPU_OUTPUT)')


def main():
    bundle=ROOT/'workspace/Server/tpusoc_shared_20261105_v1'
    if sha(bundle/'MANIFEST.sha256')!='baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83':
        raise ValueError('Original task bundle changed')
    ledger=dict(line.split('  ',1)[::-1] for line in (bundle/'MANIFEST.sha256').read_text().splitlines())
    out=ROOT/'workspace/Checks/NewPowerFirmware_20261109_v1'
    out.mkdir(exist_ok=False)
    (out/'Sw').mkdir(); (out/'BuildEvidence').mkdir()
    origins={}
    for name in ('Encoder.c','Encoder.h','Tpu.h'):
        data=subprocess.check_output(['git','-C',str(FRONT),'show',REV+':Sw/'+name])
        (out/'Sw'/name).write_bytes(data)
        origins['Sw/'+name]={'revision':REV,'sha256':hashlib.sha256(data).hexdigest()}
    for name in ('Sw/SharedMain.c','BuildEvidence/Shared.ld','BuildEvidence/SharedLayout.h'):
        source=bundle/name
        if sha(source)!=ledger[name]: raise ValueError('Original harness changed: '+name)
        data=source.read_text()
        if name=='Sw/SharedMain.c': data=adapt_main(data)
        (out/name).write_text(data,newline='\n')
        origins[name]={'original_sha256':sha(source),'change':'FF1 argument order only' if name.endswith('SharedMain.c') else 'unchanged'}
    boot=ROOT/'Sw/SharedStart.S'
    text=boot.read_text()
    if '.irp reg,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31' not in text:
        raise ValueError('Expected executable CPU GPR initialization')
    (out/'Sw/SharedStart.S').write_text(text,newline='\n')
    origins['Sw/SharedStart.S']={'sha256':sha(boot),'purpose':'31 normal instructions initialize CPU GPRs before C startup'}
    (out/'BuildEvidence/FirmwareOrigins.json').write_text(json.dumps(origins,indent=2)+'\n')
    print(out)


if __name__=='__main__': main()
