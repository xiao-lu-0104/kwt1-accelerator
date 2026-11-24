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
    from PreparePower import prepare_current
    prepare_current(out)


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
