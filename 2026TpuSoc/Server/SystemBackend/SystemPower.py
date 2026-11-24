"""Collect system-scope power estimates without changing any completed task evidence."""
import argparse
import json
import math
from pathlib import Path
import re
import tarfile
from Prepare import check,sha
from SystemTasks import saif_time,verify_review_manifest
from ClockPortReview import sdc_commands
import ReviewTaskPower
from PowerCoverage import coverage

NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
UNITS={'W':1,'mW':1e-3,'uW':1e-6,'nW':1e-9,'pW':1e-12}
SCOPE='e203_cpu_top: CPU/internal ICB + frozen accelerator + private112KiB SRAM + shared512KiB TCM; external fixed peripherals excluded'


def parse_power(text):
    result={}
    for key,label in (('internal_w','Cell Internal Power'),('switching_w','Net Switching Power'),
                      ('dynamic_w','Total Dynamic Power'),('leakage_w','Cell Leakage Power')):
        found=re.findall(re.escape(label)+r'\s*=\s*('+NUMBER+r')\s*(mW|uW|nW|pW|W)\b',text)
        if len(found)!=1: raise ValueError('Missing/duplicate power value with explicit unit: '+label)
        value=float(found[0][0])*UNITS[found[0][1]]
        if not math.isfinite(value) or value<0: raise ValueError('Invalid power value')
        result[key]=value
    if result['dynamic_w']<=0 or abs(result['dynamic_w']-result['internal_w']-result['switching_w'])>max(1e-12,result['dynamic_w']*.005):
        raise ValueError('Inconsistent dynamic power sum')
    result['total_w']=result['dynamic_w']+result['leakage_w']
    return result


def parse_macro_power(text,expected):
    matches=re.findall(r'^Totals\s*\(\s*(\d+)\s+cells\s*\)\s*(.*)$',text,re.M)
    if len(matches)!=1 or int(matches[0][0])!=expected: raise ValueError('Missing/wrong macro power total cell count')
    values=re.findall(r'('+NUMBER+r')\s*(mW|uW|nW|pW|W)\b',matches[0][1])
    if len(values)!=4: raise ValueError('Macro total lacks four explicit power units')
    result=dict(zip(('internal_w','switching_w','dynamic_w','leakage_w'),
                    (float(v)*UNITS[u] for v,u in values)))
    if any(not math.isfinite(v) or v<0 for v in result.values()): raise ValueError('Invalid macro power')
    if abs(result['dynamic_w']-result['internal_w']-result['switching_w'])>max(1e-9,result['dynamic_w']*.01):
        raise ValueError('Inconsistent macro dynamic sum')
    result['total_w']=result['dynamic_w']+result['leakage_w']; result['macro_count']=expected
    return result


def prepare(task_run,out,tools):
    record=json.loads((task_run/'Inputs.json').read_text()); check(record)
    summary=json.loads((task_run/'SystemActivitySummary.json').read_text())
    if not summary.get('both_tasks_use_same_repaired_firmware') or not summary.get('original_ff1_preserved'):
        raise ValueError('Completed two-task repaired-firmware activity required')
    check({'inputs':summary['evidence_sha256']})
    review=Path(record['review']); check(json.loads((review/'Inputs.json').read_text()))
    closed=verify_review_manifest(review)
    base=Path(record['source'])
    inputs=dict(record['inputs']); inputs.update(summary['evidence_sha256'])
    paths={'ddc':base/'mapped/candidate.ddc','sdc':review/'clock_ports_corrected.sdc',
        'std_db':Path((base/'StdDb.txt').read_text().strip()),'private_db':Path((base/'SpDb.txt').read_text().strip()),
        'shared_db':base/'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db',
        'name_map':base/'mapped/system_name_map.tcl'}
    for p in list(paths.values())+[task_run/'Inputs.json',task_run/'SystemActivitySummary.json',review/'ClockPortSummary.json']:
        inputs[str(p)]=sha(p)
    for item in closed: inputs[item['path']]=item['closed_full_sha256']
    for p in tools.iterdir():
        if p.is_file(): inputs[str(p)]=sha(p)
    # Keep complete raw unknown records; active-data guards passing does not waive
    # unknown idle/model nets for the separate power accuracy review.
    ReviewTaskPower.ROOT=('SharedTest','Cpu')
    tasks={}
    for name in ('ff1','encoder'):
        case=task_run/name; activity=summary['tasks'][name]
        if activity['status']!='PASS_PHYSICAL_TCM_TASK_AND_SYSTEM_ACTIVITY' or sha(case/'task.saif')!=activity['saif_sha256']:
            raise ValueError('Task SAIF is not the validated complete task: '+name)
        raw=(case/'task.saif').read_text(); timing=saif_time(raw)
        if abs(timing['seconds']-activity['cycles']*6.667e-9)>2e-12: raise ValueError('Activity window mismatch')
        review_x=ReviewTaskPower.saif_review(raw,{})
        if review_x['TX_records']!=activity['TX_entries'] or review_x['nonzero_TX_records']!=activity['TX_nonzero_entries']:
            raise ValueError('Raw X parser differs from validated activity inventory')
        for row in review_x['unknown']: row['category']='UNCLASSIFIED_SYSTEM_SAIF_'+row['kind']
        review_x['unknown_groups']=[]
        review_x['acceptance']='Raw SAIF inventory only; mapped relevance/effects not yet waived or accepted'
        directory=out/name; directory.mkdir()
        (directory/'RawUnknowns.json').write_text(json.dumps(review_x,indent=2)+'\n')
        inputs[str(directory/'RawUnknowns.json')]=sha(directory/'RawUnknowns.json')
        tasks[name]=activity
        print('SYSTEM_POWER_ACTIVITY:',name,'cycles='+str(activity['cycles']),
              'unknown_signals='+str(review_x['unknown_signals']),'duration_s='+str(timing['seconds']),flush=True)
    (out/'SourceNameMap.tcl').write_bytes(paths['name_map'].read_bytes())
    inputs[str(out/'SourceNameMap.tcl')]=sha(out/'SourceNameMap.tcl')
    (out/'PowerPaths.json').write_text(json.dumps({key:str(value) for key,value in paths.items()},indent=2)+'\n')
    inputs[str(out/'PowerPaths.json')]=sha(out/'PowerPaths.json')
    result={'task_run':str(task_run),'paths':{key:str(value) for key,value in paths.items()},'inputs':inputs,
        'tasks':tasks,'scope':SCOPE,'acceptance':'PENDING_COVERAGE_X_SRAM_AND_SYSTEM_BOUNDARY_REVIEW'}
    (out/'Inputs.json').write_text(json.dumps(result,indent=2)+'\n')
    print('SYSTEM_POWER_INPUTS_VERIFIED: full-system activity/checkpoint/libraries/clock view frozen; no synthesis or simulation',flush=True)


def finish(out):
    record=json.loads((out/'Inputs.json').read_text()); check(record)
    tasks={}
    for name in ('ff1','encoder'):
        directory=out/name; log=(directory/'dc.log').read_text(errors='replace')
        if 'SYSTEM_POWER_REPORT_COMPLETE:' not in log or re.search(r'^(Error:|SYSTEM_POWER_REPORT_ERROR:)',log,re.M):
            raise ValueError('System power tool failed or completion absent: '+name)
        if sdc_commands((directory/'power_view.sdc').read_text())!=sdc_commands(Path(record['paths']['sdc']).read_text()):
            raise ValueError('Power-view constraints differ from verified system clock view: '+name)
        status=dict(line.split(': ',1) for line in (directory/'tool_status.txt').read_text().splitlines() if ': ' in line)
        if status.get('NETLIST')!='UNCHANGED' or status.get('SAIF_SCOPE')!='SharedTest/Cpu': raise ValueError('System power boundary changed')
        power=parse_power((directory/'power.rpt').read_text(errors='replace'))
        macros={key:parse_macro_power((directory/filename).read_text(errors='replace'),count) for key,filename,count in (
            ('private','private_sram_power.rpt',56),('itcm','shared_itcm_power.rpt',32),('dtcm','shared_dtcm_power.rpt',32))}
        for field in ('dynamic_w','leakage_w'):
            if sum(row[field] for row in macros.values())>power[field]*1.02+1e-9:
                raise ValueError('Macro power exceeds top-level accounting: '+name+' '+field)
        hierarchy_report=(directory/'saif_hierarchy.rpt').read_text()
        if not re.search(r'(?m)^\s*-hierarchy\s*$',hierarchy_report):
            raise ValueError('Explicit full-hierarchy SAIF coverage report required: '+name)
        cov=coverage(hierarchy_report)
        top_cov=coverage((directory/'saif_coverage.rpt').read_text())
        activity=record['tasks'][name]
        result={**power,'cycles':activity['cycles'],'duration_seconds':activity['duration_seconds'],
            'task_energy_j':power['total_w']*activity['duration_seconds'],'macro_power':macros,
            'coverage':cov,'coverage_scope':'FULL_HIERARCHY_REPORT_SAIF_HIERARCHY','top_only_coverage':top_cov,
            'TX_nonzero_entries':activity['TX_nonzero_entries'],'mapping_mode':status['MAPPING_MODE'],
            'status':'SYSTEM_SCOPE_ANNOTATED_ESTIMATE_REQUIRES_COVERAGE_X_AND_BOUNDARY_REVIEW'}
        tasks[name]=result
        print('SYSTEM_POWER_ESTIMATE:',name,'total_mW='+format(power['total_w']*1000,'.9g'),
            'dynamic_mW='+format(power['dynamic_w']*1000,'.9g'),'leakage_mW='+format(power['leakage_w']*1000,'.9g'),
            'task_energy_uJ='+format(result['task_energy_j']*1e6,'.9g'),flush=True)
        print('SYSTEM_POWER_COVERAGE:',name,json.dumps(cov,sort_keys=True),flush=True)
        regions={}
        for region in ('cpu_core','accelerator','shared_tcm'):
            path=directory/('saif_'+region+'.rpt')
            if path.exists():
                try:
                    regions[region]=coverage(path.read_text())
                    print('SYSTEM_REGION_COVERAGE:',name,region,
                        'nets='+str(regions[region]['nets']['total']),
                        'net_user_percent='+str(regions[region]['nets']['user']['percent']),
                        'pins='+str(regions[region]['pins']['total']),
                        'pin_user_percent='+str(regions[region]['pins']['user']['percent']),flush=True)
                except ValueError as error:
                    print('SYSTEM_REGION_COVERAGE_REVIEW:',name,region,str(error),flush=True)
        result['regional_coverage']=regions
        for key,row in macros.items(): print('SYSTEM_SRAM_POWER:',name,key,'macros='+str(row['macro_count']),'total_mW='+format(row['total_w']*1000,'.9g'),flush=True)
        print('SYSTEM_POWER_X_REVIEW:',name,'nonzero_TX_records='+str(activity['TX_nonzero_entries']),
            'mapping='+status['MAPPING_MODE']+'; unknown activity effects still require object-level review',flush=True)
    result={'scope':SCOPE,'tasks':tasks,'task_run':record['task_run'],
        'method':'TT 1.1V 25C pre-layout saved-load DC estimate; hybrid RTL-CPU/frozen-gate-accelerator functional activity; no CTS/parasitics/SDF',
        'acceptance':'PENDING_COVERAGE_X_SRAM_MODEL_AND_FIXED_EXTERNAL_PLATFORM_BOUNDARY_REVIEW'}
    (out/'SystemPowerSummary.json').write_text(json.dumps(result,indent=2)+'\n')
    files=[p for name in ('ff1','encoder') for p in (out/name).iterdir() if p.is_file()]
    files += [out/'Inputs.json',out/'PowerPaths.json',out/'SourceNameMap.tcl',out/'SystemPowerSummary.json']
    if (out/'MappedPowerComparison.json').exists(): files.append(out/'MappedPowerComparison.json')
    if (out/'InstalledAnnotationSemantics.json').exists(): files.append(out/'InstalledAnnotationSemantics.json')
    files += [p for p in (out/'tools').iterdir() if p.is_file()]
    manifest=''.join(sha(p)+'  '+p.relative_to(out).as_posix()+'\n' for p in sorted(files))
    (out/'MANIFEST.sha256').write_text(manifest)
    package=out/'SystemPowerReports.partial.tar.gz'
    with tarfile.open(package,'x:gz') as stream:
        for p in files+[out/'MANIFEST.sha256']: stream.add(p,arcname=p.relative_to(out).as_posix(),recursive=False)
    print('SYSTEM_POWER_REPORT_ARCHIVE:',package,flush=True)
    print('RESULT: SYSTEM_POWER_REPORT_COLLECTION_COMPLETE (system-scope estimates collected; final coverage/X/boundary acceptance pending)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','finish')); parser.add_argument('out',type=Path)
    parser.add_argument('--task-run',type=Path); args=parser.parse_args()
    if args.mode=='prepare': prepare(args.task_run.resolve(),args.out.resolve(),Path(__file__).resolve().parent)
    else: finish(args.out.resolve())
