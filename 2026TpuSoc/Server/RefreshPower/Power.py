"""Parse only explicit physical power units and retain raw coverage/unknown limitations."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from Review import sha
from PowerCoverage import coverage_tables
from Tasks import check_record

NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
UNITS={'W':1,'mW':1e-3,'uW':1e-6,'nW':1e-9,'pW':1e-12}


def power_values(text):
    result={}
    for key,label in [('internal_w','Cell Internal Power'),('switching_w','Net Switching Power'),
        ('dynamic_w','Total Dynamic Power'),('leakage_w','Cell Leakage Power')]:
        matches=re.findall(re.escape(label)+r'\s*=\s*('+NUMBER+r')\s*(mW|uW|nW|pW|W)\b',text)
        if len(matches)!=1: raise ValueError('Power value lacks one explicit unit: '+label)
        value,unit=matches[0];result[key]=float(value)*UNITS[unit]
    return validate_values(result,require_dynamic=True)


def validate_values(data,require_dynamic=False):
    if any(not math.isfinite(v) or v<0 for v in data.values()): raise ValueError('Invalid physical power')
    if (require_dynamic and data['dynamic_w']<=0) or abs(data['dynamic_w']-data['internal_w']-data['switching_w'])>max(1e-12,data['dynamic_w']*.01):
        raise ValueError('Dynamic power components do not sum')
    data['total_w']=data['dynamic_w']+data['leakage_w'];return data


def group_values(text,count):
    matches=re.findall(r'^Totals\s*\(\s*(\d+)\s+cells\s*\)\s*(.*)$',text,re.M)
    if len(matches)!=1 or int(matches[0][0])!=count: raise ValueError('Group power cell count mismatch')
    values=re.findall(r'('+NUMBER+r')\s*(mW|uW|nW|pW|W)\b',matches[0][1])
    if len(values)!=4: raise ValueError('Group total needs four explicitly unit-bearing values')
    return validate_values({k:float(v)*UNITS[u] for k,(v,u) in zip(('internal_w','switching_w','dynamic_w','leakage_w'),values)})


def estimate(out,name,report_root=None,tool_root=None,limit=900):
    inputs=check_record(out/'Inputs.json')
    task=json.loads((out/name/'Activity.json').read_text())
    task_record_sha=sha(out/name/'Activity.json')
    saif=out/name/'task.saif'
    if task.get('status')!='CURRENT_TASK_GOLDEN_AND_ACTIVITY_PASS' or sha(saif)!=task['saif_sha256']:
        raise ValueError('Current successful task activity required')
    case=(report_root/name/'power') if report_root else out/name/'power'
    case.mkdir(parents=True)
    tools=tool_root or out/'tools'
    system=Path(inputs['system']);libraries=inputs['libraries']
    dc=os.environ.get('DC_BIN') or shutil.which('dc_shell')
    if not dc: raise ValueError('dc_shell not on PATH')
    env=dict(os.environ,TPU_STDCELL_DB=libraries[0],TPU_SRAM_DB=libraries[1],TPU_SYSTEM_DB=libraries[2],
        NEW_POWER_CASE=str(case),NEW_POWER_DDC=str(system/'mapped/candidate.ddc'),NEW_POWER_SAIF=str(saif),NEW_POWER_TOOLS=str(tools))
    code=subprocess.call(['python3',str(tools/'StageWatch.py'),'--label',name+'_power','--limit',str(limit),
        '--log',str(case/'dc.log'),'--cwd',str(case),'--',dc,'-f',str(tools/'Power.tcl')],env=env)
    log=(case/'dc.log').read_text(errors='replace')
    if code or 'CURRENT_TASK_POWER_REPORT_COMPLETE' not in log or re.search(r'^(Error:|CURRENT_TASK_POWER_ERROR:)',log,re.M):
        print(log[-6500:]);raise ValueError('Native current power report failed: '+name)
    status=(case/'ToolStatus.txt').read_text()
    if 'NETLIST: UNCHANGED' not in status or 'TIMING_BUDGETS: UNCHANGED' not in status: raise ValueError('Missing report-only evidence')
    total=power_values((case/'power.rpt').read_text())
    groups={}
    for line in (case/'groups.tsv').read_text().splitlines():
        key,count=line.split('\t');groups[key]=dict(group_values((case/(key+'_power.rpt')).read_text(),int(count)),leaf_count=int(count))
    for key,count in [('ACCELERATOR_PRIVATE_SRAM',56),('SHARED_ITCM_MACROS',32),('SHARED_DTCM_MACROS',32)]:
        if groups[key]['leaf_count']!=count: raise ValueError('Power SRAM accounting mismatch')
    accel={key:groups['ACCELERATOR_LOGIC_AND_INTERFACES'][key]+groups['ACCELERATOR_PRIVATE_SRAM'][key]
           for key in ('internal_w','switching_w','dynamic_w','leakage_w','total_w')}
    coverage=coverage_tables((case/'saif_global.rpt').read_text())
    hierarchical=coverage_tables((case/'saif_hierarchy.rpt').read_text())
    regional={key:coverage_tables((case/(key+'_coverage.rpt')).read_text()) for key in ('cpu_core','accelerator','shared_tcm')}
    data={'task':task,'system_power':total,'accelerator_power':accel,'groups':groups,'global_coverage_tables':coverage,
        'hierarchy_coverage_tables':hierarchical,'regional_coverage_tables':regional,
        'system_task_energy_j':total['total_w']*task['duration_seconds'],
        'accelerator_task_energy_j':accel['total_w']*task['duration_seconds'],
        'group_sum_minus_system_total_w':sum(g['total_w'] for g in groups.values())-total['total_w'],
        'acceptance':'PRE_LAYOUT_TASK_ESTIMATE; default/X/coverage and boundary review remain; not signoff'}
    check_record(out/'Inputs.json')
    if sha(saif)!=task['saif_sha256'] or sha(out/name/'Activity.json')!=task_record_sha:
        raise ValueError('Current task activity changed during power analysis')
    destination=report_root or out
    (destination/name/'PowerSummary.json').write_text(json.dumps(data,indent=2)+'\n')
    print('TASK_POWER:',name,'system_mW='+str(total['total_w']*1000),'accelerator_mW='+str(accel['total_w']*1000),flush=True)
    print('TASK_ENERGY:',name,'system_uJ='+str(data['system_task_energy_j']*1e6),flush=True)
    print('ACTIVITY_LIMITS:',name,'TX_nonzero='+str(task['TX_nonzero_entries']),'defaults/propagation kept in raw reports',flush=True)
    if len(coverage)==1:
        for kind,objects in coverage[0]['objects'].items():
            print('GLOBAL_COVERAGE:',name,kind,'total='+str(objects['total']),
                'user='+str(objects['user']['count']),'propagated='+str(objects['propagated']['count']),
                'default='+str(objects['default']['count']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);p.add_argument('--task',choices=('ff1','encoder'),required=True)
    a=p.parse_args();estimate(a.out.resolve(),a.task)
