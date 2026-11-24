"""Run the boot-only firmware repair against the existing physical-TCM simulator."""
import argparse
import json
from pathlib import Path
from Prepare import check,sha
from BootFirmware import validate_code
from SystemTasks import validate


def prepare(old,out,tools):
    record=json.loads((old/'Inputs.json').read_text()); check(record)
    activity=json.loads((old/'ff1/Activity.json').read_text())
    if sha(old/'ff1/task.saif')!=activity['saif_sha256']:
        raise ValueError('Original successful FF1 activity changed')
    failed=(old/'encoder/run.log').read_text(errors='replace')
    if 'SHARED_MACRO_WRITE_X 62' not in failed:
        raise ValueError('Original encoder failure does not match this repair')
    bundle=Path((old/'Bundle.txt').read_text().strip())
    original_fw=Path((old/'Firmware.txt').read_text().strip())
    evidence=out/'firmware/BuildEvidence'
    fix=json.loads((evidence/'BootFix.json').read_text())
    if sha(original_fw)!=fix['original_hex_sha256']:
        raise ValueError('Remote firmware differs from locally reproduced original')
    for name,digest in fix['original_inputs'].items():
        if sha(bundle/name)!=digest:
            raise ValueError('Frozen firmware source/layout differs: '+name)
    validate_code((evidence/'Shared.bin').read_bytes())
    if sha(evidence/'Firmware.hex')!=fix['fixed_hex_sha256'] or sha(evidence/'Shared.bin')!=fix['fixed_bin_sha256']:
        raise ValueError('Repaired firmware checksum mismatch')
    words=(evidence/'Firmware.hex').read_text().split()
    image=b''.join(int(word,16).to_bytes(8,'little') for word in words)
    code=(evidence/'Shared.bin').read_bytes()
    if len(words)!=32768 or image!=code+bytes(262144-len(code)):
        raise ValueError('Repaired full ITCM image differs from executable')
    # Preserve original simulator, driver, vectors, checks and completed/failed evidence.
    inputs=dict(record['inputs'])
    for name in ('Inputs.json','Task.f','Firmware.txt','Bundle.txt','simv','ff1/run.log','ff1/task.saif','ff1/Activity.json','encoder/run.log'):
        p=old/name; inputs[str(p)]=sha(p)
    runtime=old/'simv.daidir'
    if runtime.exists():
        for p in runtime.rglob('*'):
            if p.is_file(): inputs[str(p)]=sha(p)
    for root in (tools,out/'firmware'):
        for p in root.rglob('*'):
            if p.is_file(): inputs[str(p)]=sha(p)
    firmware=evidence/'Firmware.hex'
    (out/'Firmware.txt').write_text(str(firmware)+'\n')
    (out/'Bundle.txt').write_text(str(bundle)+'\n')
    for name in ('Firmware.txt','Bundle.txt'): inputs[str(out/name)]=sha(out/name)
    result=dict(record)
    result.update({'inputs':inputs,'original_task_run':str(old),
        'firmware_fix':fix,'original_ff1_saif_preserved':activity['saif_sha256'],
        'scope':'Existing original CPU RTL + frozen gate accelerator + physical macros; boot-only GPR initialization; original guards and golden checks',
        'power':'PENDING_SYSTEM_DDC_ANNOTATION_AND_COVERAGE_X_REVIEW'})
    (out/'Inputs.json').write_text(json.dumps(result,indent=2)+'\n')
    print('BOOT_FIX_PREPARED: original firmware reproduced; only boot GPR initialization changed; original simulator/FF1/failed encoder retained',flush=True)
    print('BOOT_FIX_VALIDATION: rerun BOTH tasks with the same new firmware; no X waiver, no task-time register force',flush=True)


def finish(out):
    record=json.loads((out/'Inputs.json').read_text()); check(record)
    tasks={}
    for name in ('ff1','encoder'):
        tasks[name]=json.loads((out/name/'Activity.json').read_text())
        if tasks[name]['status']!='PASS_PHYSICAL_TCM_TASK_AND_SYSTEM_ACTIVITY':
            raise ValueError('Task validation incomplete: '+name)
        if sha(out/name/'task.saif')!=tasks[name]['saif_sha256']:
            raise ValueError('Validated activity changed: '+name)
    old=Path(record['original_task_run'])
    if sha(old/'ff1/task.saif')!=record['original_ff1_saif_preserved']:
        raise ValueError('Original FF1 activity changed')
    result={'task_run':str(out),'original_task_run':str(old),'tasks':tasks,
        'firmware':record['firmware_fix'],'both_tasks_use_same_repaired_firmware':True,
        'original_ff1_preserved':True,'power':'PENDING_SYSTEM_DDC_ANNOTATION_AND_COVERAGE_X_REVIEW',
        'evidence_sha256':{str(out/name/filename):sha(out/name/filename)
            for name in tasks for filename in ('run.log','Activity.json','task.saif')}}
    (out/'SystemActivitySummary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('RESULT: BOOT_GPR_FIX_TASK_ACTIVITY_COMPLETE (both strict tasks passed with revised firmware; system power annotation remains pending)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','validate','finish')); parser.add_argument('out',type=Path)
    parser.add_argument('--task-run',type=Path); parser.add_argument('--task',choices=('ff1','encoder'))
    args=parser.parse_args()
    if args.mode=='prepare': prepare(args.task_run.resolve(),args.out.resolve(),Path(__file__).resolve().parent)
    elif args.mode=='validate': validate(args.out.resolve(),args.task)
    else: finish(args.out.resolve())
