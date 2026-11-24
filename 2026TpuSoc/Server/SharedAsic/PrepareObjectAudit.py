"""Freeze a completed SAIF review and prepare exact DC object queries."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
from ReadProbe import declarations


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def check(record):
    for filename,digest in record['inputs'].items():
        if sha(Path(filename))!=digest: raise ValueError('Frozen input changed: '+filename)


def select(previous):
    choices=[previous.resolve()] if previous else sorted(
        (Path.home()/'soc').glob('tpusoc_power_review_20261105_*'),
        key=lambda p:p.stat().st_mtime,reverse=True)
    for path in choices:
        try:
            record=json.loads((path/'ReviewInputs.json').read_text())
            check(record)
            if 'RESULT: POWER_ACTIVITY_REVIEW_COMPLETE' not in (path/'runner.log').read_text():
                raise ValueError('Read-only review incomplete')
            review=json.loads((path/'ActivityReviewSummary.json').read_text())
            source=Path(record['source'])
            if review['source']!=str(source): raise ValueError('Review/source mismatch')
            task_record=json.loads((source/'TaskPowerInputs.json').read_text())
            check(task_record)
            for task,expected in (('ff1',4370),('encoder',5924)):
                row=review['tasks'][task]
                if row['TX_records']!=82448 or row['nonzero_TX_records']!=expected:
                    raise ValueError('Expected previously confirmed unknown inventory')
                if sum(x['nonzero_TX_records'] for x in row['unknown'])!=expected:
                    raise ValueError('Unknown inventory is truncated')
            return path,record,review,task_record
        except (OSError,KeyError,ValueError):
            if previous: raise
    raise ValueError('No unchanged completed power activity review found')


def queries(review,task,log):
    requests={}
    prefix='SharedTest/Cpu/u_e203_cpu/u_e203_nice_core'
    def add(kind,name,reason):
        if not name or re.search(r'[\t\r\n"{}]',name): raise ValueError('Unsupported object name: '+repr(name))
        requests.setdefault((kind,name),set()).add(reason)
    for row in review['tasks'][task]['unknown']:
        scope=row['scope']
        if scope!=prefix and not scope.startswith(prefix+'/'): raise ValueError('Unknown lies outside frozen scope')
        relative=scope[len(prefix):].lstrip('/')
        full=(relative+'/' if relative else '')+row['signal']
        add('NET' if row['kind']=='NET' else 'PIN',full,'TX_NONZERO')
    unmatched=re.findall(r"Can't find object '([^']+)'\.\s*\(SAIF-16\)",log)
    for obj in unmatched: add('AUTO',obj,'SAIF_OBJECT_NOT_FOUND')
    for obj in ('nice_clk','Bus/Clock','Tpu/Clock','Tpu/Core/Clock'):
        add('NET',obj,'CLOCK_SOURCE_REVIEW')
    rows=[(str(i),kind,obj,','.join(sorted(reasons))) for i,((kind,obj),reasons) in enumerate(sorted(requests.items()))]
    return rows,Counter(unmatched)


def system_sources(source,out,inputs):
    functional=Path((source/'Functional.txt').read_text().strip())
    scope_path=functional/'project/Scope.json'
    scope=json.loads(scope_path.read_text())
    if scope['configuration_modified'] or scope['cpu_datapath_modified']:
        raise ValueError('Expected unchanged competition-platform CPU/configuration')
    copied=functional/'project/e203_hbirdv2/rtl/e203'
    for relative,digest in scope['copied_platform_sha256'].items():
        path=copied/relative
        if sha(path)!=digest: raise ValueError('Platform source changed: '+str(path))
        inputs[str(path)]=digest
    config=copied/'core/config.v'
    text=config.read_text()
    for kind in ('ITCM','DTCM'):
        widths=re.findall(r'(?m)^\s*`define\s+E203_CFG_'+kind+r'_ADDR_WIDTH\s+(\d+)',text)
        if widths!=['18']: raise ValueError('Expected verified 256 KiB '+kind)
    files=[]
    for line in (source/'Task.f').read_text().splitlines():
        if line and not line.startswith(('+','-')):
            path=Path(line)
            if copied in path.parents: files.append(str(path))
    memory_catalog=json.loads((source/'SystemPowerContext.json').read_text())['memory_catalog']
    macro=next((Path(item['directory']) for item in memory_catalog['available_sram_packages']
                if Path(item['directory']).name=='RAMSP4096X16'),None)
    if macro is None: raise ValueError('Verified SRAM4096 package not found')
    model=macro/'verilog/RAMSP4096X16.v'
    liberty=macro/'lib/RAMSP4096X16_tt_1p10v_1p10v_25c.lib'
    model_text=model.read_text(errors='replace')
    # Inventory all raw branches. This is evidence, not an active-branch binding.
    clean=re.sub(r'/\*.*?\*/|//[^\n]*','',model_text,flags=re.S)
    raw_declarations=declarations(clean)
    headers=re.findall(r'\bmodule\s+RAMSP4096X16\b[^;]*;',clean,re.S)
    if not headers or not raw_declarations: raise ValueError('Shared SRAM raw interface not found')
    evidence={'model':str(model),'model_sha256':sha(model),'liberty':str(liberty),
        'liberty_sha256':sha(liberty),'raw_headers':headers,'raw_declarations':raw_declarations,
        'preprocessor':[line.strip() for line in model_text.splitlines()
            if re.match(r'\s*`(?:ifdef|ifndef|elsif|else|endif|define)',line)],
        'status':'RAW_EVIDENCE_ONLY; no active-branch or functional/timing qualification claimed'}
    (out/'SharedSramMacroEvidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    organization={'platform_source':str(copied),'original_platform_scope':scope,
        'source_files':files,'new_accelerator_checkpoint':str(source/'Ddc.txt'),
        'shared_capacity_bytes':524288,'candidate_shared_macro':'RAMSP4096X16',
        'candidate_macro_count_for_capacity':64,
        'physical_binding':'PENDING_PORT_MASK_LATENCY_AND_FUNCTIONAL_VERIFICATION',
        'power_status':'CPU/interconnect/shared SRAM synthesis/activity/estimate not yet completed'}
    (out/'SystemPowerPreparation.json').write_text(json.dumps(organization,indent=2)+'\n')
    inputs[str(scope_path)]=sha(scope_path)
    inputs[str(model)]=sha(model); inputs[str(liberty)]=sha(liberty)
    print('SYSTEM_POWER_PREPARATION: unchanged platform source verified; ITCM/DTCM each 256 KiB')
    print('SHARED_SRAM_RAW_PORTS_BEGIN:',model)
    for header in headers[:3]: print(' '.join(header.split()))
    for line in raw_declarations[:28]: print(line)
    print('SHARED_SRAM_RAW_PORTS_END: active branch and byte-mask/latency checks still required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    previous,record,review,task_record=select(args.review)
    source=Path(record['source']); out=args.out.resolve()
    inputs=dict(record['inputs'])
    print('VERIFIED_ACTIVITY_REVIEW:',previous)
    print('VERIFIED_TASK_POWER:',source)
    for task in ('ff1','encoder'):
        case=out/task; case.mkdir()
        old=source/task
        log=(old/'dc.log').read_text(errors='replace')
        rows,unmatched=queries(review,task,log)
        (case/'objects.tsv').write_text('id\tkind\tname\treason\n'+''.join('\t'.join(row)+'\n' for row in rows))
        (case/'unmatched.json').write_text(json.dumps(dict(unmatched),indent=2)+'\n')
        (case/'Saif.txt').write_text(str(old/'task.saif')+'\n')
        print('OBJECT_QUERY_COUNT:',task,len(rows),'SAIF16_unique='+str(len(unmatched)))
        # Emit important warnings before the long series of SAIF-16 messages.
        lines=log.splitlines(); selected=set()
        for i,line in enumerate(lines):
            if re.search(r'\(PWR-19\)|\(PWR-452\)|\(TIM-134\)',line):
                selected.update(range(max(0,i-3),min(len(lines),i+5)))
        print('POWER_WARNING_CONTEXT_BEGIN:',task)
        for i in sorted(selected)[:60]: print(lines[i])
        print('POWER_WARNING_CONTEXT_END')
        for name in ('objects.tsv','unmatched.json','Saif.txt'): inputs[str(case/name)]=sha(case/name)
    for name in ('Ddc.txt','StdDb.txt','SpDb.txt'): shutil.copy2(source/name,out/name)
    system_sources(source,out,inputs)
    for name in ('ReviewInputs.json','ActivityReviewSummary.json','runner.log'):
        inputs[str(previous/name)]=sha(previous/name)
    for path in Path(__file__).parent.iterdir():
        if path.is_file(): inputs[str(path)]=sha(path)
    (out/'ObjectAuditInputs.json').write_text(json.dumps({'review':str(previous),'source':str(source),
        'inputs':inputs,'scope':'frozen candidate object connectivity/activity; no annotation override'},indent=2)+'\n')


if __name__=='__main__': main()
