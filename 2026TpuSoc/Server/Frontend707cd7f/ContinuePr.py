"""Audit external v6, attempt two bounded additive PG repairs, then implement 707cd7f."""
import collections
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import traceback
from PrHelpers import save,scalar,tlist,sha,tree,verify
from PgFlow import choose_source
from PgRailsInputs import select_rails
from SystemFlow import REV
from RcHelpers import select_rc,routed_nets

HERE=Path(__file__).resolve().parent
IMPLEMENT=[('01_rc',1800),('03_place',7200),('04_cts',7200),
           ('05_route',10800),('06_route_opt',7200),('07_export',1800)]


def external(soc,version,required=True):
    found=[]
    for p in soc.glob('tpusoc_pg_'+version+'_707cd7f_*'):
        lib=p/'design/system_707cd7f.nlib'
        if lib.is_dir() and (p/('conn_'+version+'.rpt')).is_file() and (p/('pg_drc_'+version+'.txt')).is_file():
            found.append((p,lib))
    if len(found)>1 or (required and len(found)!=1):
        raise ValueError('Expected one external '+version+' checkpoint with its raw reports, found '+str(len(found)))
    return found[0] if found else None


def parse_connectivity(text):
    result={};net=None;unknown=[]
    aliases={'wires':'wires','vias':'vias','stdcells':'cells','standardcells':'cells',
             'hardmacros':'macros','iopads':'pads','terminals':'terminals','ioterminals':'terminals',
             'hierarchicalblocks':'blocks','hierblocks':'blocks'}
    for line in text.splitlines():
        m=re.search(r'Verify net\s+(VDD|VSS)\s+connectivity',line,re.I)
        if m:net=m.group(1).upper();result.setdefault(net,{})
        m=re.search(r'Number of floating\s+(.+?)\s*:\s*(\d+)\s*$',line,re.I)
        if m:
            key=aliases.get(re.sub('[^a-z]','',m.group(1).lower()))
            if net is None or key is None:unknown.append(line)
            else:result[net][key]=int(m.group(2))
    known=not re.search(r'^\s*(?:Error:|Fatal:|CHECK_EXECUTION_ERROR:)',text,re.M) and not unknown and set(result)=={'VDD','VSS'} and all({'wires','vias','cells','macros'}<=set(v) for v in result.values())
    return {'known':known,'nets':result,'unknown':unknown,
            'clean':known and all(n==0 for d in result.values() for n in d.values())}


def parse_drc(text):
    total=re.findall(r'Total number of errors found\s*:\s*(\d+)',text,re.I)
    rows=[]
    for m in re.finditer(r'^\s*(\d+)\s+(.+?)\s+on\s+(\S+)\s*$',text,re.M):
        rows.append({'count':int(m.group(1)),'type':m.group(2).strip(),'layer':m.group(3)})
    value=int(total[-1]) if total else None
    known=not re.search(r'^\s*(?:Error:|Fatal:|CHECK_EXECUTION_ERROR:)',text,re.M) and value is not None and (value==0 or sum(r['count'] for r in rows)==value)
    shorts=sum(r['count'] for r in rows if 'short' in r['type'].lower()) if known else None
    return {'known':known,'total':value,'shorts':shorts,'by_type_layer':rows,'clean':known and value==0}


def detail_counts(path):
    counts=collections.Counter();kind=None;waiting=False
    if path.is_file():
        with path.open(errors='replace') as f:
            for line in f:
                m=re.match(r'\s*Error type:\s*(.*)',line)
                if m:
                    kind=m.group(1).strip() or None;waiting=kind is None
                    continue
                if waiting and line.strip():kind=line.strip();waiting=False
                m=re.match(r'\s*Layer:\s*(\S+)',line)
                if m and kind:counts[(kind,m.group(1))]+=1;kind=None
    return [{'type':k[0],'layer':k[1],'count':v} for k,v in sorted(counts.items())]


def metrics(checks):
    c,d=checks['connectivity'],checks['drc']
    if not c.get('known') or not d.get('known'):return None
    return [d['shorts'],sum(v['macros'] for v in c['nets'].values()),
            sum(v['cells'] for v in c['nets'].values()),d['total'],
            sum(v['wires']+v['vias'] for v in c['nets'].values())]


def improves(candidate,baseline):
    a,b=metrics(candidate),metrics(baseline)
    # Never buy connectivity by introducing extra DRC/shorts or new floating macros.
    return a is not None and b is not None and all(x<=y for x,y in zip(a,b)) and any(x<y for x,y in zip(a,b))


def main(out):
    cfg=json.loads((out/'Config.json').read_text());soc=Path.home()/'soc'
    source,summary=choose_source(soc,cfg['initial_package_sha256'])
    inputs=json.loads((source/'NewPrInputs.json').read_text());verify(inputs['inputs'])
    if inputs['source_commit']!=REV or sha(source/'inputs/candidate.v')!=summary['design_netlist_sha256']:
        raise ValueError('New 707cd7f source identity mismatch')
    if sha(source/'inputs/candidate.sdc')!=inputs['design_sdc_sha256']:raise ValueError('Current SDC changed')
    rails=select_rails(soc,source,cfg);audit=Path(rails['audit'])
    save(out/'ExternalDiscovery.json',{'v6_directories':[str(p) for p in soc.glob('tpusoc_pg_v6_707cd7f_*')],
         'v7_directories':[str(p) for p in soc.glob('tpusoc_pg_v7_707cd7f_*')],
         'required':'v6 design/system_707cd7f.nlib plus conn_v6.rpt and pg_drc_v6.txt at run root'})
    external_root,external_lib=external(soc,'v6')
    originals=dict(inputs['inputs']);originals.update(rails['files'])
    for p in [source/'NewPrInputs.json',source/'NewPrSummary.json',source/'inputs/candidate.v',source/'inputs/candidate.sdc']:
        originals[str(p)]=sha(p)
    snapshots={str(external_lib):tree(external_lib)};refs=[]
    evidence=out/'external_v6_evidence';evidence.mkdir()
    for n in ('PgV6.tcl','conn_v6.rpt','pg_drc_v6.txt','native.log','pg_v6.def'):
        p=external_root/n
        if p.is_file():
            originals[str(p)]=sha(p);shutil.copy2(str(p),str(evidence/n))
    for label in ('rvt','private','shared'):
        p=source/('library_'+label)/(label+'.ndm')
        expected=[h for name,h in inputs['reference_snapshots'].items() if Path(name).name==label+'.ndm']
        if len(expected)!=1 or tree(p)!=expected[0]:raise ValueError('Reference fingerprint mismatch: '+label)
        snapshots[str(p)]=expected[0];dest=out/('library_'+label)/(label+'.ndm');dest.parent.mkdir()
        shutil.copytree(str(p),str(dest))
        if tree(dest)!=expected[0]:raise ValueError('Copied reference differs')
        refs.append(dest)
    # Reuse only the previously inventoried technology data, not its old design.
    rc_inventory=[]
    for p in soc.glob('tpusoc_pr_prepare_20261109_*/RcInventory.json'):
        s=p.parent/'BackendPrepareSummary.json'
        if s.is_file() and json.loads(s.read_text()).get('result')=='NEW_1109_BACKEND_PREPARATION_COMPLETE':rc_inventory.append(p)
    if len(rc_inventory)!=1:raise ValueError('Expected one verified reference RC inventory')
    inv=rc_inventory[0];originals[str(inv)]=sha(inv)
    rc=select_rc(json.loads(inv.read_text()))
    # Exact file digests are also in RcInventory; select_rc checks mapping and both hashes.
    for p in (Path(rc['tlup']),Path(rc['map'])):originals[str(p)]=sha(p)
    phy=soc/'tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json';physical=json.loads(phy.read_text())
    originals[str(phy)]=sha(phy);icc,flag=physical['icc2'],physical['icc2_flag']
    common=tlist('RefLibs',refs)+''.join(scalar(k,v) for k,v in [
        ('BaselineLeaves',audit/'BaselineLeaves.tsv'),('BaselineMacros',audit/'BaselineMacros.tsv'),
        ('BaselineIo',source/'design/PortTerminalGeometry.tsv'),('ExpectedPeriod',inputs['expected_serialized_period_ns']),
        ('RcTlu',rc['tlup']),('RcMap',rc['map'])])
    save(out/'ContinueInputs.json',{'source_commit':REV,'source_run':str(source),'source_netlist_sha256':summary['design_netlist_sha256'],
        'external_v6':str(external_root),'original_files':originals,'library_snapshots':snapshots,
        'authorization':'two bounded PG trials, then proceed with residual PG issues retained on independent copies',
        'limits_seconds':dict(IMPLEMENT),'tools':{str(p):sha(p) for p in HERE.iterdir() if p.is_file()}})
    stages=[];trials=[];current=external_lib;last_phase=None

    def progress():
        save(out/'ContinueProgress.json',{'stages':stages,'trials':trials,'last_successful_library':str(current)})
        (out/'OpenLastCheckpoint.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')

    def run(label,action,src,limit):
        directory=out/label;directory.mkdir(parents=True)
        lib=directory/'system_707cd7f.nlib';before=tree(src)
        shutil.copytree(str(src),str(lib))
        if tree(lib)!=before or tree(src)!=before:raise ValueError('Checkpoint changed during copy; close its viewing session normally')
        (directory/'ContinueConfig.tcl').write_text(common+scalar('DesignLib',lib)+scalar('Action',action))
        log=directory/'native.log'
        code=subprocess.call(['python3',str(HERE/'StageWatch.py'),'--label',label,'--limit',str(limit),
            '--log',str(log),'--cwd',str(directory),'--',icc,flag,str(HERE/'ContinuePr.tcl')])
        text=log.read_text(errors='replace')
        done=code==0 and 'CONTINUE_PHASE_COMPLETE: '+action in text
        save(directory/'ActionResult.json',{'action':action,'native_exit':code,'complete':done,
             'core_saved':'CONTINUE_CORE_SAVED: '+action in text,'log':str(log),'library':str(lib)})
        if not done:print(text[-6000:],flush=True)
        return directory,lib,done

    def checks(tag,lib,limit=900):
        data={}
        for kind,parser in [('connectivity',parse_connectivity),('drc',parse_drc)]:
            try:
                directory,_,done=run('checks/'+tag+'/'+kind,kind,lib,limit)
                p=directory/(kind+'.rpt')
                data[kind]=parser(p.read_text(errors='replace')) if p.is_file() else {'known':False,'clean':False}
                data[kind]['executed']=done
                if not done:data[kind].update(known=False,clean=False)
                if kind=='drc':
                    data[kind]['detail_counts']=detail_counts(directory/'pg_drc_details.txt')
                    data[kind]['detail_count_matches_summary']=sum(r['count'] for r in data[kind]['detail_counts'])==data[kind].get('total')
            except Exception as error:data[kind]={'known':False,'clean':False,'executed':False,'error':str(error)}
        save(out/('PgChecks_'+tag+'.json'),data)
        print('PG_CHECKS:',tag,json.dumps(data,sort_keys=True),flush=True)
        return data

    print('SOURCE_COMMIT:',REV,flush=True)
    print('CURRENT_SYSTEM_SOURCE:',source,flush=True)
    print('EXTERNAL_PG_V6:',external_root,flush=True)
    print('MODE: bounded PG improvement then layout/CTS/route, residual violations retained, no PG waiver/signoff',flush=True)
    try:
        directory,lib,done=run('audit_v6','audit',current,900)
        if not done:raise ValueError('External v6 failed current netlist/macro/IO provenance audit; cannot use it')
        current=lib;progress()
        base=checks('baseline_v6',current)
        selected=base
        candidates=[('add_vias_v6',current)]
        low=external(soc,'v7',required=False)
        if low:
            snapshots[str(low[1])]=tree(low[1]);candidates.append(('add_vias_v7',low[1]))
        for tag,candidate in candidates:
            item={'trial':tag,'source':str(candidate),'accepted':False}
            try:
                if tag.endswith('v7'):
                    _,candidate,valid=run('audit_v7','audit',candidate,900)
                    if not valid:raise ValueError('Optional v7 failed provenance audit')
                _,repaired,done=run('trials/'+tag,'repair',candidate,600)
                if not done:raise ValueError('Installed repair command unsupported/failed; trial rejected')
                actual=checks(tag,repaired)
                item['checks']=actual
                if improves(actual,selected):
                    current=repaired;selected=actual;item['accepted']=True
                else:item['reason']='No fully measured Pareto improvement; keep previous checkpoint'
            except Exception as error:item['reason']=str(error)
            trials.append(item);progress()
        clean=all(v.get('clean') and v.get('executed') for v in selected.values())
        save(out/'PgDecision.json',{'pg_clean':bool(clean),'selected_library':str(current),'checks':selected,
             'fallback_used':not clean,'decision':'continue authorized engineering layout; residual PG issues are NOT waived'})
        if not clean:print('PG_NOT_CLEAN: continuing independent CTS/route as explicitly authorized; no waiver',flush=True)
        for phase,limit in IMPLEMENT:
            last_phase=phase
            directory,lib,done=run('stages/'+phase,phase,current,limit)
            status=json.loads((directory/'ActionResult.json').read_text());stages.append(status)
            if status['core_saved'] and (directory/'checkpoint.def').is_file():current=lib
            progress()
            if not done:raise ValueError('Implementation stopped; saved checkpoint retained: '+phase)
            current=lib;progress();print('PHASE_COMPLETE:',phase,flush=True)
        final=out/'stages/07_export'
        for n in ('routed.v','routed.sdc','checkpoint.def','setup.rpt','hold.rpt','route_check.rpt'):
            if not (final/n).is_file() or not (final/n).stat().st_size:raise ValueError('Missing final artifact '+n)
        count=routed_nets(final/'checkpoint.def')
        if count<100:raise ValueError('Missing substantial ordinary signal-net routing')
        final_checks=checks('final',current,3600)
        verify(originals)
        for p,fp in snapshots.items():
            if tree(Path(p))!=fp:raise ValueError('Original reference/checkpoint changed: '+p)
        save(out/'ContinueSummary.json',{'result':'NEW_707CD7F_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING',
             'source_commit':REV,'original_inputs_unchanged':True,'final_library':str(current),'stages':stages,
             'pg_before':base,'pg_selected_before_implementation':selected,'pg_final':final_checks,
             'ordinary_net_route_records':count,'limitations':'Actual PG/timing/route violations require review; no MCMM/LVS/IR/EM/DFT signoff; optional GDS unmerged'})
        (out/'OpenRoutedLayout.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')
        print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
        print('RESULT: NEW_707CD7F_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING',flush=True)
    except Exception:
        save(out/'ContinueFailure.json',{'last_phase':last_phase,'last_successful_library':str(current),'stages':stages,'trials':trials})
        raise
    finally:
        # Include any optional v7 selected after input ledger creation.
        save(out/'FinalOriginalLedger.json',{'files':originals,'libraries':snapshots})
        with tarfile.open(str(out/'ContinueReports.tar.gz'),'w:gz') as z:
            for p in sorted(out.rglob('*')):
                rel=p.relative_to(out)
                if p.is_file() and not any(q.endswith(('.nlib','.ndm')) for q in rel.parts) and p.name not in ('ContinueReports.tar.gz','payload.tar.gz','runner.log'):
                    z.add(str(p),arcname=rel.as_posix())


if __name__=='__main__':
    try:main(Path(sys.argv[1]).resolve())
    except Exception as error:
        print('CONTINUE_ERROR:',error,flush=True);traceback.print_exc()
        print('RESULT: NEW_707CD7F_IMPLEMENTATION_INCOMPLETE_RETAIN_CHECKPOINTS',flush=True)
        raise SystemExit(2)
