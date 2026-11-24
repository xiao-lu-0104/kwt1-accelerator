"""Fresh functional task and SAIF preparation for current accelerator/system (Python 3.6+)."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from Review import sha
from PrepareInventory import designs,inventory,monitor
from SystemTasks import shared_guard,saif_time,NUMBER
from Guards import effective_guard


def current_bench(text):
    required=['UNKNOWN_LOADER_COMMAND_READY','UNKNOWN_LOADER_RESPONSE_VALID','UNKNOWN_LOADER_READ_DATA',
        'Result !== ExpectedHost[WordIndex]','TaskActivity.StartWindow();','TaskActivity.EndRequested = 1;',
        'TcmInitializer.Done && TcmInitializer.Released']
    if any(s not in text for s in required): raise ValueError('Original strict physical task bench incomplete')
    if any(s in text for s in ('`DTCM','`ITCM','u_sirv_sim_ram.mem_r')): raise ValueError('Behavioral memory backdoor in physical bench')
    if text.count('Kind == 1 ? 99')!=2: raise ValueError('Unexpected old FF1 command count assertions')
    return text.replace('Kind == 1 ? 99','Kind == 1 ? 4')


def check_record(path,key='inputs'):
    record=json.loads(path.read_text())
    for name,digest in record[key].items():
        if sha(Path(name))!=digest: raise ValueError('Input changed: '+name)
    return record


def prepare(out):
    soc=Path.home()/'soc'
    systems=[]
    for path in soc.glob('tpusoc_new_system_dc_20261109_*'):
        record=path/'SystemSummary.json'
        if record.is_file():
            data=json.loads(record.read_text())
            if data.get('result')=='NEW_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING' and data.get('original_inputs_unchanged') is True:
                systems.append((path,data))
    if len(systems)!=1: raise ValueError('Expected one successful current system DC')
    system,result=systems[0]
    system_inputs=check_record(system/'SystemInputs.json','sha256')
    summary=result['summary']
    if summary.get('SETUP_STATUS')!='PASS' or summary.get('HOLD_STATUS')!='PASS': raise ValueError('Current system timing not PASS')
    run=Path(system_inputs['accelerator_run'])
    old=soc/'tpusoc_system_tasks_20261106_ZBysEH'
    old_record=check_record(old/'Inputs.json')
    tools=out/'tools'
    for key,digest in json.loads((out/'firmware/BuildEvidence/FirmwareEvidence.json').read_text())['sha256'].items():
        if sha(out/'firmware/BuildEvidence'/key)!=digest: raise ValueError('New firmware changed: '+key)
    binary=(out/'firmware/BuildEvidence/Shared.bin').read_bytes()
    expected=b''.join(((reg<<7)|0x13).to_bytes(4,'little') for reg in range(1,32))
    if not binary.startswith(expected): raise ValueError('Boot GPR initialization missing')
    firmware=out/'firmware/BuildEvidence/Firmware.hex'
    words=firmware.read_text().split()
    if len(words)!=32768 or b''.join(int(w,16).to_bytes(8,'little') for w in words)!=binary+bytes(262144-len(binary)):
        raise ValueError('Full ITCM image and executable disagree')
    candidate=out/'candidate.v'; shutil.copy2(system/'frozen_accelerator.v',candidate)
    if sha(candidate)!=sha(run/'mapped/candidate.v'): raise ValueError('System and standalone accelerator copies disagree')
    bench=out/'PhysicalSharedTest.sv'
    bench.write_text(current_bench((old/'PhysicalSharedTest.sv').read_text()))
    lines=(old/'Task.f').read_text().splitlines(); updated=[]; changes=[0,0]
    for line in lines:
        if line==str(old/'candidate.v'): line=str(candidate); changes[0]+=1
        if line==str(old/'PhysicalSharedTest.sv'): line=str(bench); changes[1]+=1
        updated.append(line)
    if changes!=[1,1]: raise ValueError('Old Task.f boundary mismatch')
    (out/'Task.f').write_text('\n'.join(updated)+'\n')
    model_paths=[Path(line[3:]) for line in lines if line.startswith('-v ')]
    if not model_paths: raise ValueError('No real foundry simulation models')
    models={}
    for path in model_paths:
        data=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
        models.update(designs(data.decode(errors='replace')))
    rows,opaque=inventory(designs(candidate.read_text()),models)
    (out/'Registers.json').write_text(json.dumps({'registers':rows,'opaque':dict(opaque)},indent=2))
    reset,controls=monitor(rows)
    (out/'GateResetInventory.sv').write_text(reset)
    (out/'EffectiveDataGuard.sv').write_text(effective_guard(candidate.read_text()))
    (out/'SharedTcmGuard.sv').write_text(shared_guard())
    shutil.copy2(old/'IcbMirror.sv',out/'IcbMirror.sv')
    activity=(tools/'TaskActivity.sv').read_text()
    source='SharedTest.Cpu.u_e203_cpu.u_e203_nice_core'
    if activity.count(source)!=2: raise ValueError('Unexpected activity scope template')
    activity=activity.replace(source,'SharedTest.Cpu')
    activity=activity.replace('if (Started || Stopped)',
        'if (!TcmInitializer.Done || !TcmInitializer.Released) $fatal(1,"SYSTEM_SAIF_STARTED_DURING_INIT");\n        if (Started || Stopped)')
    (out/'SystemActivity.sv').write_text(activity)
    bundle=Path((old/'Bundle.txt').read_text().strip())
    vector_paths=[]
    for folder in (bundle/'Vectors',bundle/'Vectors/Ff1_normal'):
        for name in ('Input.hex','Fractions.hex','Layer0.hex','Expected0.hex'):
            path=folder/name
            if not path.is_file(): raise ValueError('Missing golden vector: '+str(path))
            vector_paths.append(path)
    paths=dict(system_inputs['sha256']); paths.update(old_record['inputs'])
    for name in ('SystemSummary.json','SystemInputs.json','mapped/candidate.ddc','mapped/candidate.sdc','mapped/system_name_map.tcl'):
        path=system/name; paths[str(path)]=sha(path)
    for path in vector_paths+[old/'Inputs.json',old/'Task.f',old/'PhysicalSharedTest.sv',old/'IcbMirror.sv']:
        paths[str(path)]=sha(path)
    for line in updated:
        path=Path(line[3:]) if line.startswith('-v ') else Path(line) if line and not line.startswith(('+','-')) else None
        if path: paths[str(path)]=sha(path)
    for directory in (out,out/'firmware',tools):
        for path in directory.rglob('*') if directory!=out else directory.iterdir():
            if path.is_file() and '__pycache__' not in path.parts and path.name not in ('runner.log','prepare.log','payload.tar.gz'):
                paths[str(path)]=sha(path)
    libraries=[Path(line.split(None,1)[1].strip()) for line in (run/'library_sha256.txt').read_text().splitlines()]
    shared=Path(system_inputs['old_system'])/'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db'
    record={'inputs':paths,'system':str(system),'accelerator':str(run),'bundle':str(bundle),'firmware':str(firmware),
        'libraries':[str(p) for p in libraries+[shared]],'simulation':'CPU RTL + current gate accelerator + real private/shared macro models; zero delay; no SDF',
        'initial_state':'31 boot GPR instructions; pattern2 accelerator FF outputs forced for one reset clock then released; no task-time forces',
        'scope':'SharedTest/Cpu full system; initialization outside task window',
        'ff1_expected_commands':{'loads':2,'executes':4,'stores':4}}
    (out/'Inputs.json').write_text(json.dumps(record,indent=2)+'\n')
    print('NEW_TASK_PREPARED: new candidate + new block-FF1 firmware; FFs=%d controls=%d; old SAIF not reused'%(len(rows),len(controls)),flush=True)
    print('SYSTEM_SOURCE:',system,flush=True)


def validate(out,name):
    check_record(out/'Inputs.json')
    kind,values,reads,writes,loaded=(1,25344,45952,50688,45960) if name=='ff1' else (0,6336,112256,12672,112264)
    text=(out/name/'run.log').read_text(errors='replace')
    found=re.findall(r'^PASS SHARED: kind=%d layers=1 values=%d cycles=(\d+) DMA_read_bytes=%d DMA_write_bytes=%d loaded_bytes=%d$'%(kind,values,reads,writes,loaded),text,re.M)
    if len(found)!=1 or int(found[0])<=0: raise ValueError('Missing current strict golden/DMA task completion: '+name)
    cycles=int(found[0])
    required=['PASS PHYSICAL_TCM_INIT: ITCM_writes=32768 DTCM_writes=65536 ITCM_readback=32768 DTCM_readback=65536;',
        'PHYSICAL_TCM_INIT_FINAL: done=1 released=1','INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0',
        'ICB_MIRROR_FINAL: divergence_observed=0','TASK_ACTIVITY_FINAL: started=1 stopped=1',
        'EFFECTIVE_GUARD_FINAL: complete=1','SHARED_TCM_GUARD_FINAL: complete=1']
    if any(s not in text for s in required) or re.search(r'Fatal:|FATAL:|Error-\[|NEW_CONTROL_QX:',text):
        raise ValueError('Task guard failed: '+name)
    windows=re.findall(r'TASK_ACTIVITY_END: cycles=(\d+) duration_ns=([\d.]+)',text)
    if len(windows)!=1 or int(windows[0][0])!=cycles or abs(float(windows[0][1])-cycles*6.667)>.002:
        raise ValueError('Task window/cycle mismatch')
    path=out/name/'task.saif'
    with path.open() as stream: timing=saif_time(stream.read(8192))
    if abs(timing['seconds']-cycles*6.667e-9)>2e-12: raise ValueError('SAIF time header mismatch')
    cpu=sram=toggle=False; txn=tzn=0; txmax=0.0
    with path.open() as stream:
        for line in stream:
            cpu=cpu or bool(re.search(r'\(INSTANCE\s+u_e203_cpu\b',line))
            sram=sram or bool(re.search(r'\(INSTANCE\s+u_e203_srams\b',line))
            toggle=toggle or bool(re.search(r'\(TC\s+[1-9]\d*\s*\)',line))
            for value in re.findall(r'\(TX\s+('+NUMBER+r')\s*\)',line):
                number=float(value); txn+=int(number>0); txmax=max(txmax,number)
            for value in re.findall(r'\(TZ\s+('+NUMBER+r')\s*\)',line): tzn+=int(float(value)>0)
    if not cpu or not sram or not toggle: raise ValueError('SAIF scope or switching incomplete')
    data={'status':'CURRENT_TASK_GOLDEN_AND_ACTIVITY_PASS','task':name,'cycles':cycles,'duration_seconds':timing['seconds'],
        'saif_sha256':sha(path),'saif_bytes':path.stat().st_size,'TX_nonzero_entries':txn,'TZ_nonzero_entries':tzn,
        'max_individual_TX_fraction':txmax/float(timing['raw_duration']),'saif_time_header':timing,
        'unknown_waiver':False,'scope':'full CPU/system task; initialization excluded'}
    (out/name/'Activity.json').write_text(json.dumps(data,indent=2)+'\n')
    print('CURRENT_TASK_PASS:',name,'cycles='+str(cycles),'duration_s='+str(timing['seconds']),'TX_nonzero='+str(txn),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','validate'));p.add_argument('out',type=Path)
    p.add_argument('--task',choices=('ff1','encoder'));a=p.parse_args()
    if a.mode=='prepare':prepare(a.out.resolve())
    else:validate(a.out.resolve(),a.task)


if __name__=='__main__':main()
