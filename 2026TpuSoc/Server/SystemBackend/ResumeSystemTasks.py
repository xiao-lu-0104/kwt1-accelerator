"""Resume after an SAIF validator format failure; retain successful simulation."""
import argparse
import json
from pathlib import Path
from Prepare import check,sha
from SystemTasks import validate


def prepare(old,out,tools):
    record=json.loads((old/'Inputs.json').read_text()); check(record)
    text=(old/'runner.log').read_text()
    if 'STAGE_FINISHED: compile exit=0' not in text or 'STAGE_FINISHED: simulate_ff1 exit=0' not in text:
        raise ValueError('Original compile and FF1 simulation completion not verified')
    for name in ('run.log','task.saif'):
        if (old/'encoder'/name).exists(): raise ValueError('Encoder output already exists; refusing overwrite')
    if (old/'ff1/Activity.json').exists(): raise ValueError('FF1 already validated; inspect completed results')
    inputs=dict(record['inputs'])
    for name in ('Inputs.json','runner.log','simv','compile.log','ff1/run.log','ff1/task.saif','Bundle.txt','Firmware.txt'):
        p=old/name; inputs[str(p)]=sha(p)
    for p in tools.iterdir():
        if p.is_file(): inputs[str(p)]=sha(p)
    saved={'task_run':str(old),'inputs':inputs,'mode':'reuse original compiled binary and successful FF1 SAIF; run only missing encoder',
        'FF1_SAIF_sha256':sha(old/'ff1/task.saif')}
    head=(old/'ff1/task.saif').read_text()[:4096]
    for line in head.splitlines():
        if 'TIMESCALE' in line.upper() or 'DURATION' in line.upper(): print('EXISTING_SAIF_HEADER:',line.strip(),flush=True)
    validate(old,'ff1')
    inputs[str(old/'ff1/Activity.json')]=sha(old/'ff1/Activity.json')
    check({'inputs':inputs})
    (out/'ResumeInputs.json').write_text(json.dumps(saved,indent=2)+'\n')
    print('RESUME_INPUTS_VERIFIED: original inputs/binary/FF1 activity frozen; no recompile or FF1 rerun',flush=True)


def finish(out):
    record=json.loads((out/'ResumeInputs.json').read_text()); check(record)
    old=Path(record['task_run'])
    validate(old,'encoder')
    tasks={name:json.loads((old/name/'Activity.json').read_text()) for name in ('ff1','encoder')}
    files={str(old/name/filename):sha(old/name/filename) for name in tasks for filename in ('run.log','task.saif','Activity.json')}
    result={'task_run':str(old),'resume':str(out),'tasks':tasks,'evidence_sha256':files,
        'power':'PENDING_SYSTEM_DDC_ANNOTATION_AND_COVERAGE_X_REVIEW',
        'FF1_preserved':sha(old/'ff1/task.saif')==record['FF1_SAIF_sha256']}
    if not result['FF1_preserved']: raise ValueError('Previously successful FF1 activity changed')
    (out/'SystemActivitySummary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('RESULT: SYSTEM_PHYSICAL_TCM_TASK_ACTIVITY_COMPLETE (original FF1 retained; encoder validated; system DDC power annotation next)',flush=True)
    print('SYSTEM_TASK_RUN:',old,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('prepare','finish'))
    p.add_argument('out',type=Path); p.add_argument('--task-run',type=Path)
    a=p.parse_args()
    if a.mode=='prepare': prepare(a.task_run.resolve(),a.out.resolve(),Path(__file__).resolve().parent)
    else: finish(a.out.resolve())
