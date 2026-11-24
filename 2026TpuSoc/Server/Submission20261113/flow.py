"""Explicit, resumable DC / activity-power / basic PR runner for the new frontend.

Old TCM/AXI128 integrations are deliberately not auto-selected. Final source
lists, topology and simulator adapters cannot be bound until the new commit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from evaluate import load, save, sha, git_revision, validate_evidence, verify_vectors

HERE=Path(__file__).resolve().parent


def tcl(value):
    value=str(value)
    if any(x in value for x in ['{','}','\n','\r']):
        raise ValueError('Unsupported Tcl word '+repr(value))
    return '{'+value.replace('\\','/')+'}'


def paths(config, kind):
    root=Path(config['source_root']).resolve()
    values=config['targets'][kind]
    return root,values


def check(config):
    if not config.get('frontend_bound') or 'PENDING' in json.dumps(config):
        raise ValueError('FRONTEND_PENDING: wait for new commit, review SysBus32 and bind config; never run old integration')
    root=Path(config['source_root']).resolve()
    if git_revision(root)!=config['source_commit']:
        raise ValueError('Source HEAD differs from bound revision')
    if (root/'.git').exists() and subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no']).strip():
        raise ValueError('Source tracked files changed')
    review=load(config['topology_review'])
    if review.get('source_commit')!=config['source_commit']:
        raise ValueError('Topology review belongs to another commit')
    for key,value in {'platform_bus_width':32,'shared_sram_bytes':524288,
                       'dma_route':'original_system_bus','loader_route':'original_system_bus',
                       'result_route':'original_system_bus','direct_tcm_access':False,
                       'parallel_bypass_port':False,'preloaded_task_weights':False}.items():
        if review.get(key)!=value:
            raise ValueError('QA topology requirement failed: '+key)
    if not review.get('reviewed_connections'):
        raise ValueError('Record actual instance/port connections, not only approval booleans')
    for relative,digest in review['rtl_evidence_sha256'].items():
        if sha(root/relative)!=digest:
            raise ValueError('Reviewed topology source changed: '+relative)
    if config['clock_hz']!=150000000:
        raise ValueError('Expected 150 MHz')
    if not config['sram_dbs']:
        raise ValueError('All real private/shared SRAM DBs must be provided')
    for p in [config['stdcell_db']]+config['sram_dbs']:
        if not Path(p).is_file():raise ValueError('Missing library '+p)
    for kind in ['accelerator','system']:
        _,v=paths(config,kind)
        if not v['sources'] or not v['macro_counts']:
            raise ValueError('Bind actual sources and macro counts for '+kind)
        for name in v['sources']:
            if not (root/name).is_file():raise ValueError('Missing RTL '+name)
        if not (root/v['constraints']).is_file():raise ValueError('Missing reviewed SDC/Tcl '+v['constraints'])
    return review


def native(command, cwd, expected):
    """No destructive elapsed-time watchdog: preserve long native EDA work."""
    log=cwd/'native.log'
    if log.exists():
        raise ValueError('Stage already attempted: inspect checkpoint/log; use a new attempt directory')
    with log.open('wb') as stream:
        process=subprocess.Popen(command,cwd=str(cwd),stdout=stream,stderr=subprocess.STDOUT)
        started=time.monotonic()
        print('RUNNING pid={} LOG={}'.format(process.pid,log),flush=True)
        while process.poll() is None:
            time.sleep(5)
            elapsed=int(time.monotonic()-started)
            if elapsed and elapsed%60<5:
                print('HEARTBEAT elapsed={}s log_bytes={}'.format(elapsed,log.stat().st_size),flush=True)
    text=log.read_text(errors='replace')
    if process.returncode or expected not in text or '\nError:' in text:
        raise ValueError('Native stage incomplete; retain '+str(cwd)+'; inspect native.log')


def write_config(config,out,kind,mode):
    root,v=paths(config,kind)
    lines=[]
    def scalar(k,value):lines.append('set '+k+' '+tcl(value))
    def listing(k,values):lines.append('set '+k+' [list '+' '.join(tcl(x) for x in values)+']')
    scalar('Top',v['top']);scalar('StdDb',config['stdcell_db']);listing('SramDbs',config['sram_dbs'])
    listing('Sources',[root/p for p in v['sources']]);listing('Includes',[root/p for p in v['include_dirs']])
    listing('Defines',v['defines']);scalar('ConstraintFile',root/v['constraints']);scalar('ClockPort',v['clock_port'])
    scalar('SourceCommit',config['source_commit']);scalar('ExpectedPeriod',6.666667)
    listing('MacroCounts',sum(([ref,str(count)] for ref,count in sorted(v['macro_counts'].items())),[]))
    scalar('Mode',mode);scalar('Tools',HERE)
    if kind=='system':scalar('AcceleratorScope',v['accelerator_scope'])
    (out/'Config.tcl').write_text('\n'.join(lines)+'\n')


def dc(config,out,kind,accelerator=None):
    frozen=None
    if kind=='system':
        if accelerator is None:raise ValueError('System DC must reuse/freeze current accelerator DDC; supply --accelerator')
        frozen=load(accelerator/'Complete.json')
        if frozen['source_commit']!=config['source_commit'] or frozen['target']!='accelerator':raise ValueError('Wrong accelerator candidate')
        if sha(accelerator/'candidate.v')!=frozen['netlist_sha256']:raise ValueError('Accelerator candidate changed')
    out.mkdir(parents=True,exist_ok=False)
    write_config(config,out,kind,'compile')
    if frozen:
        with (out/'Config.tcl').open('a') as f:
            f.write('set AcceleratorDdc '+tcl(accelerator/'candidate.ddc')+'\n')
            f.write('set FrozenAcceleratorTop '+tcl(config['targets']['accelerator']['top'])+'\n')
    root,v=paths(config,kind)
    save(out/'Inputs.json',{'source_commit':config['source_commit'],'target':kind,
        'files':{str(root/p):sha(root/p) for p in v['sources']+[v['constraints']]},
        'libraries':{p:sha(p) for p in [config['stdcell_db']]+config['sram_dbs']}})
    native([config['dc_bin'],'-f',str(HERE/'Dc.tcl')],out,'DC_REPORTS_COMPLETE')
    if not all((out/p).is_file() and (out/p).stat().st_size for p in ['candidate.ddc','candidate.v','candidate.sdc','Metrics.tsv']):
        raise ValueError('DC output missing')
    if frozen:
        def metric(p):return dict(line.split('\t',1) for line in p.read_text().splitlines() if '\t' in line)
        before=float(metric(accelerator/'Metrics.tsv')['mapped_leaf_area_um2'])
        after=float(metric(out/'Metrics.tsv')['accelerator_leaf_area_um2'])
        if abs(before-after)>.01:raise ValueError('Frozen accelerator area changed during system DC; do not combine results')
    timing=dict(line.split('\t',1) for line in (out/'Metrics.tsv').read_text().splitlines() if '\t' in line)
    if min(float(timing['setup_wns_ns']),float(timing['hold_wns_ns']))<0:
        raise ValueError('DC reports saved but timing fails; inspect setup.rpt/hold.rpt and recover from baseline before continuing')
    save(out/'Complete.json',{'source_commit':config['source_commit'],'target':kind,
         'status':'DC_REPORTS_COMPLETE_REVIEW_TIMING','netlist_sha256':sha(out/'candidate.v')})
    print('DC_REPORTS_COMPLETE',out)


def hold(config,out,kind,baseline):
    if load(baseline/'Inputs.json')['source_commit']!=config['source_commit']:
        raise ValueError('Cannot recover another revision')
    out.mkdir(parents=True,exist_ok=False);write_config(config,out,kind,'hold')
    with (out/'Config.tcl').open('a') as f:f.write('set BaselineDdc '+tcl(baseline/'baseline.ddc')+'\n')
    native([config['dc_bin'],'-f',str(HERE/'Dc.tcl')],out,'DC_REPORTS_COMPLETE')
    timing=dict(line.split('\t',1) for line in (out/'Metrics.tsv').read_text().splitlines() if '\t' in line)
    if min(float(timing['setup_wns_ns']),float(timing['hold_wns_ns']))<0:raise ValueError('Recovered candidate still fails timing; retained')
    if kind=='system':
        before=dict(line.split('\t',1) for line in (baseline/'Metrics.tsv').read_text().splitlines() if '\t' in line)
        if abs(float(before['accelerator_leaf_area_um2'])-float(timing['accelerator_leaf_area_um2']))>.01:
            raise ValueError('System hold repair changed frozen accelerator area')
    save(out/'Inputs.json',load(baseline/'Inputs.json'))
    save(out/'Complete.json',{'source_commit':config['source_commit'],'target':kind,
         'status':'HOLD_REPORTS_COMPLETE_NEW_GATE_COMPARISON_REQUIRED','netlist_sha256':sha(out/'candidate.v')})
    print('HOLD_REPORTS_COMPLETE',out,'; perform new equivalence check before acceptance')


def power(config,out,dcdir,vectors):
    d=load(dcdir/'Complete.json');manifest=load(vectors/'Evaluation.json')
    verify_vectors(vectors,manifest)
    if d['source_commit']!=config['source_commit'] or d['target']!='system':
        raise ValueError('Power requires current full-system DDC')
    if sha(dcdir/'candidate.v')!=d['netlist_sha256']:
        raise ValueError('Frozen netlist changed')
    result=validate_evidence(vectors,manifest,load(vectors/'RunEvidence.json'),config['source_commit'])
    activity=load(vectors/'Activity.json')
    if activity.get('simulation_kind') not in ['gate_accelerator_cpu_rtl','full_system_gate']:
        raise ValueError('Bind a current gate-containing simulation, not RTL-only activity')
    if activity['source_commit']!=config['source_commit'] or activity['netlist_sha256']!=d['netlist_sha256']:
        raise ValueError('Activity and current netlist not paired')
    if activity.get('effective_data_x_count')!=0 or not activity.get('initialization_release_checked'):
        raise ValueError('Task X or initialization guard failed')
    records=activity['tasks']
    if [r['id'] for r in records]!=[r['id'] for r in result['task_windows']]:raise ValueError('SAIF tasks/order differ')
    out.mkdir(parents=True,exist_ok=False)
    from power_summary import power_values,group_values
    import re
    estimates=[]
    for record,window in zip(records,result['task_windows']):
        saif=vectors/record['saif']
        if sha(saif)!=record['saif_sha256'] or not math_close(record['duration_seconds'],window['duration_seconds']):
            raise ValueError('SAIF/window evidence mismatch')
        with saif.open(errors='replace') as stream:head=stream.read(16384)
        ts=re.search(r'\(TIMESCALE\s+([\d.]+)\s+(ps|ns|us|ms|s)\s*\)',head)
        duration=re.search(r'\(DURATION\s+([\d.eE+-]+)\s*\)',head)
        if not ts or not duration:raise ValueError('Missing native SAIF time header')
        actual_seconds=float(ts.group(1))*float(duration.group(1))*{'ps':1e-12,'ns':1e-9,'us':1e-6,'ms':1e-3,'s':1}[ts.group(2)]
        if not math_close(actual_seconds,window['duration_seconds']):raise ValueError('Native SAIF duration differs from timed task')
        stage=out/record['id'];stage.mkdir();write_config(config,stage,'system','power')
        with (stage/'Config.tcl').open('a') as f:
            f.write('set CurrentDdc '+tcl(dcdir/'candidate.ddc')+'\nset ActivityFile '+tcl(saif)+'\n')
            f.write('set ActivityInstance '+tcl(config['targets']['system']['saif_instance'])+'\n')
        native([config['dc_bin'],'-f',str(HERE/'Power.tcl')],stage,'POWER_REPORTS_COMPLETE')
        values=power_values((stage/'power.rpt').read_text())
        accel=group_values((stage/'accelerator_power.rpt').read_text(),int((stage/'AcceleratorCount.txt').read_text()))
        estimates.append(dict(window,system_power_w=values['total_w'],system_energy_j=values['total_w']*window['duration_seconds'],
                              accelerator_power_w=accel['total_w']))
    save(out/'TaskWindow.json',result)
    energy=sum(x['system_energy_j'] for x in estimates)
    save(out/'PowerSummary.json',{'status':'REPORTS_COMPLETE_COVERAGE_REVIEW_PENDING','source_commit':config['source_commit'],
         'tasks':estimates,'batch_energy_j':energy,'average_power_w':energy/result['duration_seconds'],
         'energy_per_task_j':energy/len(estimates),'coverage_acceptance':'PENDING_FULL_HIERARCHY_DEFAULT_PROPAGATION_X_REVIEW'})
    print('POWER_REPORTS_COMPLETE_COVERAGE_REVIEW_REQUIRED',out)


def gate_check(config,dcdir,vectors):
    command=config['gate_check_command']
    if not command:raise ValueError('Bind current gate simulation command after frontend arrives')
    complete=load(dcdir/'Complete.json')
    if complete['source_commit']!=config['source_commit']:raise ValueError('Wrong gate revision')
    env=dict(os.environ,EVAL_VECTOR_ROOT=str(vectors),EVAL_SOURCE_COMMIT=config['source_commit'],
             EVAL_GATE_NETLIST=str(dcdir/'candidate.v'),EVAL_GATE_NETLIST_SHA256=sha(dcdir/'candidate.v'))
    subprocess.check_call(command,env=env)
    validate_evidence(vectors,load(vectors/'Evaluation.json'),load(vectors/'RunEvidence.json'),config['source_commit'])
    print('GATE_TASK_OUTPUTS_AND_BUS_TRACE_VALIDATED; review Activity.json and gate scope')


def math_close(a,b):return abs(float(a)-float(b))<=max(1e-12,abs(float(b))*1e-6)


def pr(config,out,dcdir,retry=False):
    d=load(dcdir/'Complete.json')
    if d['source_commit']!=config['source_commit'] or sha(dcdir/'candidate.v')!=d['netlist_sha256']:
        raise ValueError('PR must use the current frozen netlist')
    if not config['reference_ndms']:raise ValueError('Missing reusable physical reference libraries')
    for p in config['reference_ndms']+[config['technology_tf'],config['rc_tluplus'],config['rc_map']]:
        if not Path(p).exists():raise ValueError('Missing PR input '+p)
    out.mkdir(parents=True,exist_ok=True)
    stages=['01_import_io','02_pg_place','03_build_clock','04_route_clock','05_route','06_export','07_checks']
    for index,name in enumerate(stages):
        stage=out/name
        if (stage/'Complete.json').is_file():
            if load(stage/'Complete.json')['source_commit']!=config['source_commit']:raise ValueError('PR revision changed')
            continue
        if stage.exists() and retry:
            stage.rename(out/(name+'_failed_'+time.strftime('%Y%m%d_%H%M%S')))
        stage.mkdir(exist_ok=False);write_config(config,stage,'system','pr')
        if index:
            previous=out/stages[index-1]/'design.nlib'
            shutil.copytree(str(previous),str(stage/'design.nlib'))
        with (stage/'Config.tcl').open('a') as f:
            for k,v in [('Action',name),('DesignLib',stage/'design.nlib'),('CurrentNetlist',dcdir/'candidate.v'),
                        ('CurrentSdc',dcdir/'candidate.sdc'),('Technology',config['technology_tf']),
                        ('RcTlu',config['rc_tluplus']),('RcMap',config['rc_map'])]:f.write('set '+k+' '+tcl(v)+'\n')
            f.write('set RefLibs [list '+' '.join(tcl(p) for p in config['reference_ndms'])+']\n')
        native([config['icc2_bin'],'-file',str(HERE/'Pr.tcl')],stage,'PR_STAGE_COMPLETE')
        save(stage/'Complete.json',{'source_commit':config['source_commit'],'stage':name,
                                   'quality':'violations retained; see native reports'})
    (out/'OpenLayout.tcl').write_text('open_lib '+tcl(out/'06_export/design.nlib')+'\nopen_block '+tcl(config['targets']['system']['top'])+'\nstart_gui\n')
    print('BASIC_PR_EXECUTED_REVIEW_REPORTS',out)


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['preflight','dc-accelerator','dc-system','hold-accelerator','hold-system','gate-check','power','pr'])
    p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path)
    p.add_argument('--dc',type=Path);p.add_argument('--vectors',type=Path);p.add_argument('--baseline',type=Path)
    p.add_argument('--accelerator',type=Path,help='Current frozen accelerator candidate for system synthesis')
    p.add_argument('--retry',action='store_true',help='Retain failed PR directory and retry from previous saved stage')
    a=p.parse_args();config=load(a.config);check(config)
    if a.stage=='preflight':print('PREFLIGHT_READY');return
    if a.stage=='gate-check':gate_check(config,a.dc.resolve(),a.vectors.resolve());return
    out=a.out.resolve()
    if a.stage.startswith('dc-'):dc(config,out,a.stage[3:],a.accelerator.resolve() if a.accelerator else None)
    elif a.stage.startswith('hold-'):hold(config,out,a.stage[5:],a.baseline.resolve())
    elif a.stage=='power':power(config,out,a.dc.resolve(),a.vectors.resolve())
    elif a.stage=='pr':pr(config,out,a.dc.resolve(),a.retry)


if __name__=='__main__':
    try:main()
    except Exception as e:print('FLOW_STOPPED:',e,file=sys.stderr);sys.exit(2)
