"""Audit existing system power reports, full hierarchy coverage and installed mapping docs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from Prepare import check,sha
from PowerCoverage import coverage_tables


def relevant_lines(path,pattern,limit=30):
    if not path.exists(): return ['FILE_NOT_PRESENT: '+str(path)]
    lines=path.read_text(errors='replace').splitlines(); chosen=set()
    for index,line in enumerate(lines):
        if re.search(pattern,line,re.I): chosen.update(range(max(0,index-1),min(len(lines),index+3)))
    selected=sorted(chosen)[:limit]
    return [str(i+1)+': '+lines[i][:240] for i in selected] or lines[:min(8,len(lines))]


def run(source,out,tools):
    record=json.loads((source/'Inputs.json').read_text()); check(record)
    summary=json.loads((source/'SystemPowerSummary.json').read_text())
    inputs=dict(record['inputs'])
    for line in (source/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1); path=(source/name).resolve()
        if source not in path.parents or sha(path)!=digest: raise ValueError('Original system report changed: '+name)
        inputs[str(path)]=digest
    for name in ('Inputs.json','MANIFEST.sha256','SystemPowerSummary.json'):
        inputs[str(source/name)]=sha(source/name)
    for path in tools.iterdir():
        if path.is_file(): inputs[str(path)]=sha(path)
    print('SYSTEM_POWER_REVIEW_SOURCE:',source,flush=True)
    print('MODE: existing reports/docs/X inventories read only; no DC, simulation, synthesis or activity changes',flush=True)
    result={'source':str(source),'tasks':{},'mapping_documentation':{},'acceptance':'PENDING_GLOBAL_COVERAGE_MAPPING_AND_X_EFFECT_REVIEW'}
    for name in ('ff1','encoder'):
        case=source/name; power=summary['tasks'][name]
        print('EXISTING_SYSTEM_ESTIMATE:',name,'total_mW='+str(power['total_w']*1000),
              'energy_uJ='+str(power['task_energy_j']*1e6),flush=True)
        reports={}
        for filename in ('saif_coverage.rpt','saif_hierarchy.rpt','saif_missing.rpt'):
            path=case/filename
            if not path.exists():
                print('COVERAGE_FILE_ABSENT:',name,filename,flush=True); continue
            text=path.read_text(errors='replace')
            try: tables=coverage_tables(text)
            except ValueError as error:
                reports[filename]={'parse_error':str(error),'header':text.splitlines()[:35]}
                print('COVERAGE_PARSE_REVIEW:',name,filename,str(error),flush=True)
                for line in text.splitlines()[:16]: print('COVERAGE_HEADER:',line[:200],flush=True)
                continue
            reports[filename]={'tables':tables,'table_count':len(tables)}
            # Distinct row sets are retained; no sum of inclusive hierarchy tables.
            counts=[{'line':t['line'],'nets':t['objects']['nets']['total'],
                'pins':t['objects']['pins']['total'],'ports':t['objects']['ports']['total'],
                'user_net_percent':t['objects']['nets']['user']['percent'],
                'user_pin_percent':t['objects']['pins']['user']['percent']} for t in tables]
            print('COVERAGE_TABLES:',name,filename,'count='+str(len(tables)),json.dumps(counts[:4],sort_keys=True),flush=True)
            # The report title and preceding instance/design label are required to
            # decide whether a row is global, a top-only view, or a local module.
            first=tables[0]
            if name=='ff1':
                context=[line for line in first['context'] if line.strip() and not re.fullmatch(r'[-*\s]+',line)]
                for line in context[-8:]: print('COVERAGE_CONTEXT:',name,filename,line[:220],flush=True)
            if len(tables)>1:
                last=tables[-1]
                labels=[line.strip() for line in last['context'] if re.search(r'instance|design|hierarch|cell|total',line,re.I)]
                print('COVERAGE_LAST_TABLE:',name,filename,json.dumps(counts[-1]),'context='+repr(labels[-3:]),flush=True)
        raw=json.loads((case/'RawUnknowns.json').read_text()); unknown=raw['unknown']
        blocks=Counter()
        for row in unknown:
            scope=row['scope'].split('/'); relative=scope[2:] if scope[:2]==['SharedTest','Cpu'] else scope
            blocks['/'.join(relative[:3]) or '<system_top>']+=1
        print('SYSTEM_X_BLOCKS:',name,json.dumps(dict(blocks.most_common(8)),sort_keys=True),flush=True)
        examples=sorted(unknown,key=lambda row:row['TX_fraction'],reverse=True)[:3]
        for row in examples:
            print('SYSTEM_X_EXAMPLE:',name,json.dumps({key:row.get(key) for key in ('scope','signal','TX_fraction','kind')},sort_keys=True),flush=True)
        result['tasks'][name]={'estimate':power,'coverage_reports':reports,'unknown_blocks':dict(blocks),
            'unknown_signals':len(unknown),'no_unknown_waiver':True}
    mapping=source/'SourceNameMap.tcl'; text=mapping.read_text(errors='replace')
    commands=Counter(re.findall(r'(?m)^\s*([A-Za-z_][A-Za-z_0-9]*)\b',text))
    sample=[line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')][:5]
    result['name_map']={'sha256':sha(mapping),'bytes':mapping.stat().st_size,'command_counts':dict(commands),'sample':sample}
    print('SYNTHESIS_NAME_MAP:',json.dumps({'bytes':mapping.stat().st_size,'commands':dict(commands)},sort_keys=True),flush=True)
    for line in sample: print('SYNTHESIS_NAME_MAP_SAMPLE:',line[:240],flush=True)
    base=Path(record['paths']['ddc']).parent
    documents=[source/'ff1/read_saif_help.txt',source/'ff1/read_saif_manual.txt',base/'read_saif_help.txt',
        base/'read_saif_manual.txt',base/'saif_map_help.txt',base/'saif_map_manual.txt']
    seen_documents=set()
    for path in documents:
        if path.exists():
            digest=sha(path); inputs[str(path)]=digest
            if digest in seen_documents:
                print('INSTALLED_MAPPING_DOC_DUPLICATE:',path,flush=True); continue
            seen_documents.add(digest)
        lines=relevant_lines(path,r'auto_map|map_names|name.map|mapping|source|read_saif|saif_map|create_map|write_map',16)
        print('INSTALLED_MAPPING_DOC:',path,flush=True)
        for line in lines: print(line,flush=True)
        result['mapping_documentation'][str(path)]=lines
    check({'inputs':inputs})
    (out/'Inputs.json').write_text(json.dumps({'inputs':inputs,'source':str(source)},indent=2)+'\n')
    (out/'SystemPowerReview.json').write_text(json.dumps(result,indent=2)+'\n')
    print('RESULT: SYSTEM_POWER_REPORT_REVIEW_COLLECTED (original power/activity/report bytes unchanged; inspect full hierarchy coverage and mapping evidence)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    parser.add_argument('--source',type=Path,required=True); args=parser.parse_args()
    run(args.source.resolve(),args.out.resolve(),Path(__file__).resolve().parent)
