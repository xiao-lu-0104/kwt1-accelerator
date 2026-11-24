"""Checkpointed 1109 system implementation through PG, place, CTS and routing."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

HERE=Path(__file__).resolve().parent
PHASES=[('01_rc',900),('02_pg',2400),('03_place',3600),('04_cts',3600),
        ('05_route',7200),('06_route_opt',3600),('07_export',1800)]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def verify(record):
    for name,digest in record.items():
        if sha(name)!=digest:raise ValueError('Input changed: '+name)


def tree(root):
    result={};total=0
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('Library symlink requires review: '+str(p))
        if p.is_file():
            total+=p.stat().st_size
            if total>4*1024**3 or len(result)>60000:raise ValueError('Library snapshot exceeds limit')
            result[p.relative_to(root).as_posix()]=sha(p)
    if not result:raise ValueError('Empty library: '+str(root))
    return result


def scalar(name,value):
    value=str(value)
    if any(c in value for c in '{}\\\r\n'):raise ValueError('Unsafe Tcl value')
    return 'set '+name+' {'+value+'}\n'


def tlist(name,values):
    for value in values:scalar('x',value)
    return 'set '+name+' [list '+' '.join('{'+str(v)+'}' for v in values)+']\n'


def layer_map(text):
    sections={};current=None
    for line in text.splitlines():
        fields=line.split('#',1)[0].strip().split()
        if not fields or fields[0].startswith(';'):continue
        if fields[0] in ('conducting_layers','via_layers','marker_layers','remove_layers'):
            current=fields[0];sections[current]={};continue
        if current and len(fields)>=2:sections[current][fields[0]]=fields[1]
    return sections


def select_rc(inventory):
    if inventory['map_inventory']['truncated']:raise ValueError('Mapping inventory incomplete')
    rc=[r for r in inventory['rc_candidates'] if Path(r['path']).name=='StarRC_40LL_1P8M_1TM_TYP.tluplus']
    maps=[m for m in inventory['map_inventory']['candidates'] if Path(m['path']).name=='StarRC_40LL_1P8M_1TM_cell.map']
    pairs=[(r,m) for r in rc for m in maps if Path(r['path']).parent==Path(m['path']).parent]
    if len(pairs)!=1:raise ValueError('Expected unique same-directory RVT 1P8M_1TM TYP/map pair')
    r,m=pairs[0];verify({r['path']:r['sha256'],m['path']:m['sha256']})
    mapping=layer_map(Path(m['path']).read_text())
    conduct={'GT':'npoly','ALPA':'alpa','TM2':'metal8'}
    conduct.update({'M'+str(i):'metal'+str(i) for i in range(1,8)})
    vias={'CT':'npolyCont','TV2':'via7','PA':'viapa'}
    vias.update({'V'+str(i):'via'+str(i) for i in range(1,7)})
    if mapping.get('conducting_layers')!=conduct or mapping.get('via_layers')!=vias:
        raise ValueError('RC mapping is not the native M1..M7+TM2 one-thick-metal stack')
    return {'tlup':r['path'],'map':m['path'],'mapping':mapping,
        'model':'TYP1109','corner':'INITIAL','early_late':'same TYP, 25C engineering trial; not MCMM worst-corner signoff'}


def operational_errors(text):
    checking=False;errors=[]
    for line in text.splitlines():
        if line.startswith('FULL_PR_CHECK_BEGIN:'):checking=True
        elif line.startswith('FULL_PR_CHECK_END:'):checking=False
        elif re.match(r'^\s*Fatal:',line) or (re.match(r'^\s*Error:',line) and not checking):errors.append(line)
    return errors


def routed_nets(path):
    inside=False;count=0
    with path.open(errors='replace') as f:
        for line in f:
            if re.match(r'^\s*NETS\s+\d+',line):inside=True
            elif re.match(r'^\s*END\s+NETS',line):inside=False
            elif inside and re.search(r'\+\s+(?:ROUTED|FIXED|COVER)\b',line):count+=1
    return count


def main(out):
    soc=Path.home()/'soc';good=[]
    for p in soc.glob('tpusoc_pr_prepare_20261109_*'):
        if (p/'BackendPrepareSummary.json').is_file():
            d=json.loads((p/'BackendPrepareSummary.json').read_text())
            if d.get('result')=='NEW_1109_BACKEND_PREPARATION_COMPLETE' and d.get('source_unchanged') is True:good.append(p)
    if len(good)!=1:raise ValueError('Expected one successful current backend preparation')
    source=good[0];record=json.loads((source/'BackendPrepareInputs.json').read_text())
    verify(record['inputs']);verify(record['tools'])
    system=Path(record['design_source'])
    if '20261109' not in system.name or sha(system/'mapped/candidate.v')!=record['design_netlist_sha256']:
        raise ValueError('Not the unchanged 1109 full system')
    if sha(system/'mapped/candidate.sdc')!=record['design_sdc_sha256']:raise ValueError('System SDC changed')
    overview=(source/'design/BackendOverview.txt').read_text()
    for pattern in (r'LEAVES: 154817\b',r'MACROS: RAMSP1024X16 56\b',r'MACROS: RAMSP4096X16 64\b',
                    r'M7 layer_type interconnect routing_direction horizontal',r'TM2 layer_type interconnect routing_direction vertical'):
        if not re.search(pattern,overview):raise ValueError('Native source/stack evidence changed: '+pattern)
    inventory=json.loads((source/'RcInventory.json').read_text());rc=select_rc(inventory)
    original=dict(record['inputs']);snapshots={};refs=[]
    for n in ('BackendPrepareInputs.json','BackendPrepareSummary.json','RcInventory.json','design/BackendOverview.txt'):
        original[str(source/n)]=sha(source/n)
    for label in ('rvt','private','shared'):
        src=source/('library_'+label)/(label+'.ndm');dst=out/('library_'+label)/(label+'.ndm')
        snapshots[str(src)]=tree(src);dst.parent.mkdir();shutil.copytree(str(src),str(dst))
        if tree(dst)!=snapshots[str(src)]:raise ValueError('Reference copy mismatch')
        refs.append(dst)
    first=source/'design/system_1109.nlib';snapshots[str(first)]=tree(first)
    physical=json.loads((soc/'tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json').read_text())
    icc=physical['icc2'];flag=physical['icc2_flag']
    bound={'source':str(source),'design_source':str(system),'netlist_sha256':record['design_netlist_sha256'],
        'sdc_sha256':record['design_sdc_sha256'],'inputs':original,'source_library_snapshots':snapshots,
        'rc':rc,'scope':'1109 e203_cpu_top CPU + private56/shared64',
        'limits_seconds':dict(PHASES),'tools':{str(p):sha(p) for p in HERE.iterdir() if p.is_file()}}
    save(out/'FullPrInputs.json',bound)
    print('CURRENT_1109_DESIGN:',system,flush=True)
    print('CURRENT_NETLIST_SHA256:',record['design_netlist_sha256'],flush=True)
    print('RC_TYP:',rc['tlup'],'MAP:',rc['map'],flush=True)
    print('MODE: checkpoint per phase; TYP TT engineering trial; actual violations retained',flush=True)
    current=first;stages=[];failed=None
    try:
        for phase,limit in PHASES:
            directory=out/'stages'/phase;directory.mkdir(parents=True)
            lib=directory/'system_1109.nlib';before=tree(current)
            shutil.copytree(str(current),str(lib))
            if tree(lib)!=before:raise ValueError('Checkpoint copy mismatch')
            config=''.join(scalar(k,v) for k,v in [('Phase',phase),('DesignLib',lib),('RcTlu',rc['tlup']),('RcMap',rc['map'])])
            config+=tlist('RefLibs',refs)
            (directory/'FullConfig.tcl').write_text(config)
            print('PHASE_BEGIN:',phase,flush=True)
            log=directory/'icc2.log'
            code=subprocess.call(['python3',str(HERE/'StageWatch.py'),'--label',phase,'--limit',str(limit),
                '--log',str(log),'--cwd',str(directory),'--',icc,flag,str(HERE/'FullStage.tcl')])
            text=log.read_text(errors='replace')
            status={'phase':phase,'native_exit':code,'log':str(log),'library':str(lib),
                'complete':code==0 and 'FULL_PR_PHASE_COMPLETE: '+phase in text and not operational_errors(text)}
            stages.append(status);save(out/'FullPrProgress.json',{'stages':stages,'last_successful_library':str(current)})
            if not status['complete']:
                print(text[-10000:],flush=True);failed=phase;raise ValueError('Native phase failed: '+phase)
            if not (directory/'checkpoint.def').is_file():raise ValueError('Missing phase DEF')
            current=lib
            (out/'OpenLastCheckpoint.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')
            save(out/'FullPrProgress.json',{'stages':stages,'last_successful_library':str(current)})
            print('PHASE_COMPLETE:',phase,'LIBRARY:',lib,flush=True)
        final=out/'stages/07_export'
        for n in ('routed.v','routed.sdc','checkpoint.def','qor.rpt','setup.rpt','hold.rpt','route_check.rpt','pg_connectivity.rpt','pg_drc.rpt'):
            if not (final/n).is_file() or (final/n).stat().st_size==0:raise ValueError('Missing final output: '+n)
        routed=routed_nets(final/'checkpoint.def')
        if routed<100:raise ValueError('DEF lacks substantial ordinary-net route records')
        review=[]
        for stage in stages:
            status=Path(stage['log']).parent/'PrStatus.tsv'
            if status.is_file():
                for line in status.read_text().splitlines():
                    if line.startswith('CHECK_EXECUTION\t') and re.search(r'\bcode=[1-9]',line):
                        review.append({'phase':stage['phase'],'check':line})
        verify(original)
        for p,fingerprint in snapshots.items():
            if tree(Path(p))!=fingerprint:raise ValueError('Original initial-layout/reference changed')
        (out/'OpenRoutedLayout.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')
        save(out/'FullPrSummary.json',{'result':'NEW_1109_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING','stages':stages,
            'original_inputs_unchanged':True,'design_source':str(system),'final_library':str(current),
            'ordinary_net_route_records':routed,'final_outputs':str(final),'rc':rc,
            'check_execution_issues':review,
            'acceptance':'native flow and routed artifacts complete; actual timing/DRC/PG/LVS review remains, not signoff'})
        print('ORDINARY_NET_ROUTE_RECORDS:',routed,flush=True)
        print('CHECK_EXECUTION_ISSUES:',len(review),'inspect raw timing/DRC/PG reports even if zero',flush=True)
        print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
        print('OPEN_GUI:',icc,flag,str(out/'OpenRoutedLayout.tcl'),flush=True)
        print('RESULT: NEW_1109_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING',flush=True)
    except Exception:
        save(out/'FullPrFailure.json',{'failed_phase':failed,'stages':stages,'last_successful_library':str(current),
            'message':'retain all checkpoints; resume from last success, no DC/power rerun'})
        raise


if __name__=='__main__':
    try:main(Path(sys.argv[1]).resolve())
    except Exception as error:
        print('FULL_PR_ERROR:',error,flush=True);traceback.print_exc()
        print('RESULT: NEW_1109_FULL_PR_INCOMPLETE_RETAIN_CHECKPOINTS',flush=True)
        raise SystemExit(2)
