"""Revalidate saved current tasks and retry only power in a new directory."""
import json
from pathlib import Path
import re
import shutil
import sys
import traceback


def main():
    out=Path(sys.argv[1]).resolve()
    candidates=[]
    for source in (Path.home()/'soc').glob('tpusoc_current_power_20261109_*'):
        if all((source/name/'Activity.json').is_file() and (source/name/'task.saif').is_file() for name in ('ff1','encoder')):
            candidates.append(source)
    if len(candidates)!=1:
        raise ValueError('Expected exactly one saved current two-task run, found '+str(len(candidates)))
    source=candidates[0]
    print('ORIGINAL_RUN:',source,flush=True)
    tools=out/'tools';tools.mkdir()
    for path in (source/'tools').iterdir():
        if path.is_file():shutil.copy2(str(path),str(tools/path.name))
    for name in ('Power.py','Power.tcl'):
        shutil.copy2(str(out/'replacement'/name),str(tools/name))
    sys.path.insert(0,str(tools))
    from Tasks import check_record,validate
    from Review import sha
    from Power import estimate
    record=check_record(source/'Inputs.json')
    previous=(source/'ff1_power_runner.log').read_text(errors='replace')
    evidence=[line for line in previous.splitlines() if re.match(r'STAGE_(TIMEOUT|FINISHED|RUNNING):',line)]
    for line in evidence[-8:]:print('PREVIOUS_NATIVE_STAGE:',line,flush=True)
    timeout=bool(re.search(r'^STAGE_TIMEOUT: ff1_power\s*$',previous,re.M))
    print('PREVIOUS_NATIVE_TIMEOUT_CONFIRMED:',timeout,flush=True)
    print('RECOVERY: no synthesis, compilation or simulation; new reports only; native cap 3600 seconds per task',flush=True)
    proof=out/'validation';proof.mkdir()
    shutil.copy2(str(source/'Inputs.json'),str(proof/'Inputs.json'))
    activity_sha={}
    for name in ('ff1','encoder'):
        case=proof/name;case.mkdir()
        original=json.loads((source/name/'Activity.json').read_text())
        activity_sha[name]=sha(source/name/'Activity.json')
        for file in ('run.log','task.saif'):
            shutil.copy2(str(source/name/file),str(case/file))
        validate(proof,name)
        fresh=json.loads((case/'Activity.json').read_text())
        if fresh!=original:raise ValueError('Saved and independently revalidated activity differ: '+name)
        print('REUSED_TASK_VALIDATED:',name,json.dumps(original,sort_keys=True),flush=True)
    (out/'RecoveryInputs.json').write_text(json.dumps({'source':str(source),'original_inputs':record,
        'activity_sha256':activity_sha,'previous_stage_evidence':evidence,'timeout_confirmed':timeout,
        'recovery_files':{str(p):sha(p) for p in tools.iterdir() if p.is_file()}},indent=2)+'\n')
    for name in ('ff1','encoder'):
        estimate(source,name,report_root=out,tool_root=tools,limit=3600)
    check_record(source/'Inputs.json')
    for name,digest in activity_sha.items():
        if sha(source/name/'Activity.json')!=digest:raise ValueError('Original activity changed')
    data={name:json.loads((out/name/'PowerSummary.json').read_text()) for name in ('ff1','encoder')}
    (out/'CurrentPowerSummary.json').write_text(json.dumps({'tasks':data,'source':str(source),
        'result':'CURRENT_SYSTEM_TASK_POWER_REPORTS_COMPLETE_REVIEW_PENDING',
        'scope':'fresh 20261109 task SAIF, original current DDC; TT pre-layout estimate; default/X/coverage review remains'},indent=2)+'\n')
    print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
    print('RESULT: CURRENT_SYSTEM_TASK_POWER_REPORTS_COMPLETE_REVIEW_PENDING',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('POWER_RECOVERY_ERROR:',error,flush=True)
        traceback.print_exc()
        print('RESULT: POWER_RECOVERY_INCOMPLETE; retain reports and inspect last POWER_STEP',flush=True)
        raise SystemExit(2)
