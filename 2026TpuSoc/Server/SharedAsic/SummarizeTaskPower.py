"""Validate complete task windows and retain power estimates with coverage limits."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from PreparePower import fingerprints
from SummarizePower import saif_duration_seconds

TASKS={'ff1':(1,25344,332348,45952,50688,45960),
       'encoder':(0,6336,1485712,112256,12672,112264)}
NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def validate_activity(directory, name):
    kind,values,cycles,reads,writes,loaded=TASKS[name]
    text=(directory/'run.log').read_text(errors='replace')
    required=[f'PASS SHARED: kind={kind} layers=1 values={values} cycles={cycles} DMA_read_bytes={reads} DMA_write_bytes={writes} loaded_bytes={loaded}',
              'INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0',
              'ICB_MIRROR_FINAL: divergence_observed=0',
              'TASK_ACTIVITY_FINAL: started=1 stopped=1']
    if any(item not in text for item in required) or re.search(r'Fatal:|FATAL:|Error-\[|NEW_CONTROL_QX:',text):
        raise ValueError('Task did not pass strict golden/initialization checks: '+name)
    matches=re.findall(r'TASK_ACTIVITY_END: cycles=(\d+) duration_ns=('+NUMBER+r')',text)
    if len(matches)!=1 or int(matches[0][0])!=cycles:
        raise ValueError('Missing/duplicate/wrong task activity window')
    expected=cycles*6.667e-9
    observed=float(matches[0][1])*1e-9
    if abs(observed-expected)>2e-12: raise ValueError('Simulation window mismatch')
    path=directory/'task.saif'
    saif=path.read_text(errors='strict')
    duration=saif_duration_seconds(saif)
    if abs(duration-expected)>2e-12: raise ValueError('SAIF window mismatch')
    if not re.search(r'\(TC\s+[1-9]\d*\s*\)',saif): raise ValueError('No nonzero task activity')
    tx=[float(x) for x in re.findall(r'\(TX\s+('+NUMBER+r')\s*\)',saif)]
    tz=[float(x) for x in re.findall(r'\(TZ\s+('+NUMBER+r')\s*\)',saif)]
    raw_duration=float(re.search(r'\(DURATION\s+('+NUMBER+r')\s*\)',saif)[1])
    return {'task':name,'cycles':cycles,'duration_seconds':duration,
        'simulation_clock_period_ns':6.667,'constraint_clock_period_ns':6.666667,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'saif_bytes':path.stat().st_size,
        'TX_entries':len(tx),'TX_nonzero_entries':sum(x>0 for x in tx),
        'TZ_nonzero_entries':sum(x>0 for x in tz),
        'max_individual_TX_fraction':max(tx,default=0)/raw_duration,
        'unknown_review':'Unknowns are retained; their effect must be reviewed before final acceptance'}


def parse_power(text):
    result={}
    for name,label in (('internal_w','Cell Internal Power'),('switching_w','Net Switching Power'),
                       ('dynamic_w','Total Dynamic Power'),('leakage_w','Cell Leakage Power')):
        match=re.search(re.escape(label)+r'\s*=\s*('+NUMBER+r')\s*(mW|uW|nW|pW|W)\b',text)
        if not match: raise ValueError('Missing explicit power value/unit: '+label)
        value=float(match[1])*{'W':1,'mW':1e-3,'uW':1e-6,'nW':1e-9,'pW':1e-12}[match[2]]
        if not math.isfinite(value) or value<0: raise ValueError('Invalid power: '+label)
        result[name]=value
    if abs(result['dynamic_w']-result['internal_w']-result['switching_w'])>max(1e-12,result['dynamic_w']*0.005):
        raise ValueError('Dynamic power sum inconsistent')
    if result['dynamic_w']<=0: raise ValueError('Zero dynamic power requires investigation')
    result['total_w']=result['dynamic_w']+result['leakage_w']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    parser.add_argument('--check-activity',choices=TASKS)
    args=parser.parse_args()
    out=args.out.resolve()
    fingerprints(json.loads((out/'TaskPowerInputs.json').read_text()))
    if args.check_activity:
        activity=validate_activity(out/args.check_activity,args.check_activity)
        (out/args.check_activity/'ActivityReview.json').write_text(json.dumps(activity,indent=2)+'\n')
        print('TASK_ACTIVITY_VALIDATED:',json.dumps(activity,sort_keys=True))
        return
    records=[]
    print('TASK_POWER_SUMMARY:')
    for name in TASKS:
        directory=out/name
        activity=validate_activity(directory,name)
        record=dict(activity)
        status=(directory/'dc_status.txt').read_text().strip()
        if status=='PASS':
            try:
                power=parse_power((directory/'power.rpt').read_text(errors='replace'))
                record.update(power)
                record['task_energy_j']=power['total_w']*activity['duration_seconds']
                record['status']='ANNOTATED_ESTIMATE_REQUIRES_COVERAGE_AND_X_REVIEW'
                print(f'TASK_ESTIMATE: {name} internal_W={power["internal_w"]:.9g} switching_W={power["switching_w"]:.9g} leakage_W={power["leakage_w"]:.9g} total_W={power["total_w"]:.9g} energy_J={record["task_energy_j"]:.9g}')
            except ValueError as error:
                record['status']='POWER_REPORT_REQUIRES_REVIEW'
                record['error']=str(error)
        else: record['status']='POWER_TOOL_FAILED_SEE_DC_LOG'
        print('TASK_STATUS:',name,record['status'])
        print('TASK_X_REVIEW:',name,'TX_nonzero_entries='+str(activity['TX_nonzero_entries']),
              'max_individual_TX_fraction='+str(activity['max_individual_TX_fraction']))
        for report in ('saif_coverage.rpt','saif_hierarchy.rpt','private_sram_power.rpt','power.rpt'):
            path=directory/report
            if path.exists():
                print('REPORT_BEGIN:',name,report)
                lines=path.read_text(errors='replace').splitlines()
                print('\n'.join(lines if len(lines)<=100 else lines[:70]+['... full report retained ...']+lines[-25:]))
                print('REPORT_END:',name,report)
        records.append(record)
    output={'scope':'accelerator+112KiB private SRAM; CPU/interconnect/shared SRAM excluded',
            'estimation':'TT pre-layout, zero-delay gate activity, saved net loads; no CTS/parasitics/SDF',
            'tasks':records,'system_power':'PENDING_CPU_INTERCONNECT_SHARED_SRAM',
            'acceptance':'Not final: annotation coverage, X activity, SRAM power, load assumptions require review'}
    (out/'TaskPowerSummary.json').write_text(json.dumps(output,indent=2)+'\n')
    print('SYSTEM_TOTAL_POWER: NOT_ESTABLISHED; accelerator result cannot substitute contest system power')
    print('POWER_ACCEPTANCE: PENDING_ANNOTATION_X_SRAM_AND_SYSTEM_REVIEW')


if __name__=='__main__': main()
