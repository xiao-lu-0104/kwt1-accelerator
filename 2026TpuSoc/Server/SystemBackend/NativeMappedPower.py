"""Re-estimate existing system activity with its saved native synthesis name map."""
import argparse
import json
from pathlib import Path
import re
import shutil
from Prepare import check,sha
from PowerCoverage import coverage
from SystemPower import finish as finish_power,parse_power


def manifest(source):
    result={}
    for line in (source/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1); path=(source/name).resolve()
        if source not in path.parents or sha(path)!=digest: raise ValueError('Original power report changed: '+name)
        result[str(path)]=digest
    return result


def prepare(source,out,tools):
    record=json.loads((source/'Inputs.json').read_text()); check(record)
    inputs=dict(record['inputs']); inputs.update(manifest(source))
    old=json.loads((source/'SystemPowerSummary.json').read_text())
    native=Path(record['paths']['name_map'])
    header=native.read_text(errors='strict')[:2048]
    if not re.search(r'(?m)^\s*SAIF name mapping file\s*$',header) or not re.search(r'(?m)^\s*design\s+e203_cpu_top\s*$',header):
        raise ValueError('Expected original native Power Compiler mapping data for e203_cpu_top')
    if sha(native)!=sha(source/'SourceNameMap.tcl'): raise ValueError('Original and archived synthesis name maps differ')
    base=Path(record['paths']['ddc']).parent
    saif_manual=source/'ff1/read_saif_manual.txt'; map_manual=base/'saif_map_manual.txt'
    if '-map_names' not in saif_manual.read_text() or '-read_map' not in map_manual.read_text():
        raise ValueError('Installed read_saif/saif_map documentation must support saved native maps')
    baseline={}
    for name in ('ff1','encoder'):
        case=source/name
        raw=(case/'saif_hierarchy.rpt').read_text()
        if not re.search(r'(?m)^\s*-hierarchy\s*$',raw): raise ValueError('Original hierarchy coverage report required')
        baseline[name]=coverage(raw)
        directory=out/name; directory.mkdir()
        shutil.copy2(case/'RawUnknowns.json',directory/'RawUnknowns.json')
        inputs[str(directory/'RawUnknowns.json')]=sha(directory/'RawUnknowns.json')
    for name in ('PowerPaths.json','SourceNameMap.tcl'):
        shutil.copy2(source/name,out/name); inputs[str(out/name)]=sha(out/name)
    for path in (saif_manual,map_manual,source/'Inputs.json',source/'SystemPowerSummary.json',source/'MANIFEST.sha256',native):
        inputs[str(path)]=sha(path)
    for path in tools.iterdir():
        if path.is_file(): inputs[str(path)]=sha(path)
    result=dict(record)
    result.update({'inputs':inputs,'previous_power_source':str(source),'baseline_global_coverage':baseline,
        'baseline_estimates':old['tasks'],'mapping':'Native saif_map -read_map followed by read_saif -map_names; no Tcl source or activity override'})
    (out/'Inputs.json').write_text(json.dumps(result,indent=2)+'\n')
    print('NATIVE_POWER_PREPARED: unchanged system DDC/both validated SAIFs; original native name map verified against installed manuals',flush=True)
    print('MAPPING_DATA:',native,'bytes='+str(native.stat().st_size)+'; read as native data, never sourced as Tcl',flush=True)
    for name,value in baseline.items():
        print('BASELINE_GLOBAL_COVERAGE:',name,'nets='+str(value['nets']['total']),
            'net_user_percent='+str(value['nets']['user']['percent']),'pins='+str(value['pins']['total']),
            'pin_user_percent='+str(value['pins']['user']['percent']),flush=True)


def finish(out,expected_mode='NATIVE_SYNTHESIS_MAP_READ_SAIF_MAP_NAMES',
           expected_external='LOADED_WITH_SAIF_MAP_READ_MAP',result_name='NATIVE_MAPPED_SYSTEM_POWER_COMPLETE'):
    record=json.loads((out/'Inputs.json').read_text()); check(record)
    # Confirm native mapping was actually loaded before writing any completion.
    for name in ('ff1','encoder'):
        status=(out/name/'tool_status.txt').read_text()
        if 'MAPPING_MODE: '+expected_mode not in status or 'EXTERNAL_NAME_MAP: '+expected_external not in status:
            raise ValueError('Expected annotation strategy was not used: '+name)
        if record.get('require_active_mapping') and 'NAME_MAPPING_LIFECYCLE: STARTED_BEFORE_DDC' not in status:
            raise ValueError('Mapping lifecycle completion evidence missing: '+name)
    comparison={}
    for name in ('ff1','encoder'):
        before=record['baseline_global_coverage'][name]
        after=coverage((out/name/'saif_hierarchy.rpt').read_text())
        row=parse_power((out/name/'power.rpt').read_text())
        changes={}
        for key in ('nets','ports','pins'):
            if before[key]['total']!=after[key]['total']: raise ValueError('Coverage inventories changed: '+name+' '+key)
            changes[key]={'total':after[key]['total'],'before_user_percent':before[key]['user']['percent'],
                'after_user_percent':after[key]['user']['percent'],
                'extra_user_annotated':after[key]['user']['count']-before[key]['user']['count'],
                'default_count':after[key]['default']['count'],'propagated_count':after[key]['propagated']['count']}
        comparison[name]={'coverage':changes,'previous_total_w':record['baseline_estimates'][name]['total_w'],
            'mapped_total_w':row['total_w'],'default_or_X_waiver':False}
    (out/'MappedPowerComparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    finish_power(out)
    for name,result in comparison.items():
        print('MAPPED_GLOBAL_COVERAGE_CHANGE:',name,json.dumps(result['coverage'],sort_keys=True),flush=True)
        print('MAPPED_POWER_CHANGE:',name,'old_mW='+format(record['baseline_estimates'][name]['total_w']*1000,'.9g'),
            'new_mW='+format(result['mapped_total_w']*1000,'.9g'),flush=True)
    print('RESULT:',result_name,'(full-hierarchy coverage reported; inspect remaining defaults/X; no final power waiver)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('mode',choices=('prepare','finish'))
    parser.add_argument('out',type=Path); parser.add_argument('--source',type=Path); args=parser.parse_args()
    if args.mode=='prepare': prepare(args.source.resolve(),args.out.resolve(),Path(__file__).resolve().parent)
    else: finish(args.out.resolve())
