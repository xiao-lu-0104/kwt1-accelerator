"""Fingerprint failed encoder evidence and prepare a passive-only write trace."""
import argparse
import json
from pathlib import Path
from Prepare import check,sha


def prepare(old,out,tools):
    record=json.loads((old/'Inputs.json').read_text()); check(record)
    activity=json.loads((old/'ff1/Activity.json').read_text())
    if sha(old/'ff1/task.saif')!=activity['saif_sha256']: raise ValueError('Passed FF1 SAIF changed')
    failed=(old/'encoder/run.log').read_text(errors='replace')
    if 'SHARED_MACRO_WRITE_X 62' not in failed or 'TASK_ACTIVITY_FINAL: started=1 stopped=0' not in failed:
        raise ValueError('Expected incomplete encoder with macro62 write-X failure')
    inputs=dict(record['inputs'])
    for name in ('Inputs.json','ff1/Activity.json','ff1/task.saif','ff1/run.log','encoder/run.log','Task.f','Bundle.txt','Firmware.txt'):
        p=old/name; inputs[str(p)]=sha(p)
    for p in tools.iterdir():
        if p.is_file(): inputs[str(p)]=sha(p)
    (out/'Inputs.json').write_text(json.dumps({'task_run':str(old),'inputs':inputs,
        'scope':'Passive final macro/CPU register/write/PC trace added; no DUT/firmware/task/guard changes',
        'purpose':'Identify unknown data source before changing initialization or reviewing power'},indent=2)+'\n')
    print('ENCODER_TRACE_PREPARED: original FF1 and failed encoder retained; original fatal guards unchanged',flush=True)


def finish(out):
    record=json.loads((out/'Inputs.json').read_text()); check(record)
    text=(out/'run.log').read_text(errors='replace')
    labels=('CPU_WRITE_TRACE:','CPU_DTCM_WRITE:','MACRO62_WRITE:','CPU_GPRS:','CPU_RECENT_FETCH_PC:')
    found=[line for line in text.splitlines() if line.startswith(labels) or 'SHARED_MACRO_WRITE_X' in line]
    if not all(any(line.startswith(label) for line in found) for label in labels): raise ValueError('Diagnostic did not capture all required passive evidence')
    (out/'WriteTrace.txt').write_text('\n'.join(found)+'\n')
    print('\n'.join(found),flush=True)
    print('RESULT: ENCODER_WRITE_DIAGNOSTIC_COMPLETE (evidence only; encoder golden and system power remain pending)',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('prepare','finish'))
    p.add_argument('out',type=Path); p.add_argument('--task-run',type=Path)
    a=p.parse_args()
    if a.mode=='prepare': prepare(a.task_run.resolve(),a.out.resolve(),Path(__file__).resolve().parent)
    else: finish(a.out.resolve())
