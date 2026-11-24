"""Resume the confirmed 1109 PG timeout in a separate, fingerprinted workspace."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from FullRun import sha, save, verify, tree, scalar, tlist, operational_errors, routed_nets, select_rc

HERE = Path(__file__).resolve().parent
PHASES = [('02_pg',2400),('03_place',3600),('04_cts',3600),
          ('05_route',7200),('06_route_opt',3600),('07_export',1800)]


def find_source(soc):
    candidates = []
    for p in soc.glob('tpusoc_full_pr_20261109_*'):
        if not (p/'runner.log').is_file() or not (p/'FullPrFailure.json').is_file():
            continue
        log = (p/'runner.log').read_text(errors='replace')
        failure = json.loads((p/'FullPrFailure.json').read_text())
        if ('STAGE_TIMEOUT: 02_pg' in log and
            'PHASE_COMPLETE: 01_rc' in log and failure.get('failed_phase') == '02_pg'):
            candidates.append(p)
    if len(candidates) != 1:
        raise ValueError('Expected exactly one confirmed original 1109 PG timeout')
    return candidates[0]


def run_native(out, directory, label, limit, script, icc, flag):
    log = directory/'icc2.log'
    code = subprocess.call(['python3',str(HERE/'StageWatch.py'),'--label',label,
        '--limit',str(limit),'--log',str(log),'--cwd',str(directory),
        '--',icc,flag,str(HERE/script)])
    text = log.read_text(errors='replace')
    return code, text, log


def main(out):
    source = find_source(Path.home()/'soc')
    bound = json.loads((source/'FullPrInputs.json').read_text())
    failure = json.loads((source/'FullPrFailure.json').read_text())
    first = source/'stages/01_rc/system_1109.nlib'
    if Path(failure['last_successful_library']) != first:
        raise ValueError('Unexpected original last successful checkpoint')
    rc_log = (first.parent/'icc2.log').read_text(errors='replace')
    if 'FULL_PR_PHASE_COMPLETE: 01_rc' not in rc_log:
        raise ValueError('Missing native RC completion evidence')
    verify(bound['inputs']); verify(bound['tools'])
    for p, fingerprint in bound['source_library_snapshots'].items():
        if tree(Path(p)) != fingerprint:
            raise ValueError('Original initial/reference library changed: '+p)
    original = dict(bound['inputs'])
    for n in ('FullPrInputs.json','FullPrFailure.json','runner.log','stages/01_rc/icc2.log'):
        original[str(source/n)] = sha(source/n)
    snapshots = {str(first):tree(first)}
    refs = []
    for label in ('rvt','private','shared'):
        src = source/('library_'+label)/(label+'.ndm')
        dst = out/('library_'+label)/(label+'.ndm')
        snapshots[str(src)] = tree(src)
        expected = bound['source_library_snapshots'][str(Path(bound['source'])/('library_'+label)/(label+'.ndm'))]
        if snapshots[str(src)] != expected:
            raise ValueError('Original full-run reference differs from prepared source')
        dst.parent.mkdir(); shutil.copytree(str(src),str(dst))
        if tree(dst) != snapshots[str(src)]:
            raise ValueError('Reference copy mismatch')
        refs.append(dst)
    physical = json.loads((Path.home()/'soc/tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json').read_text())
    icc, flag = physical['icc2'], physical['icc2_flag']
    rc = bound['rc']
    if select_rc(json.loads((Path(bound['source'])/'RcInventory.json').read_text())) != rc:
        raise ValueError('Selected RC files or mapping changed')
    save(out/'RecoveryInputs.json',{'source':str(source),'design_source':bound['design_source'],
        'netlist_sha256':bound['netlist_sha256'],'original_files':original,
        'library_snapshots':snapshots,'rc':rc,'phases':PHASES,
        'changes':['check_std_cell_pins all','save core checkpoint before reports',
                   'connectivity in isolated process after PG','DRC in isolated process after export'],
        'tools':{str(p):sha(p) for p in HERE.iterdir() if p.is_file()}})
    current = first; stages = []; checks = []; failed = None

    def progress():
        save(out/'RecoveryProgress.json',{'stages':stages,'checks':checks,'last_successful_library':str(current)})
        (out/'OpenLastCheckpoint.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')

    def check(kind, limit):
        directory = out/('checks/'+kind); directory.mkdir(parents=True)
        # Checks open a separate copy; a timeout cannot damage the implementation checkpoint.
        lib = directory/'system_1109.nlib'
        before = tree(current); shutil.copytree(str(current),str(lib))
        if tree(lib) != before: raise ValueError('Check checkpoint copy mismatch')
        (directory/'FullConfig.tcl').write_text(scalar('DesignLib',lib)+tlist('RefLibs',refs)+scalar('CheckKind',kind))
        code,text,log = run_native(out,directory,'check_'+kind,limit,'PgCheck.tcl',icc,flag)
        completed = code == 0 and 'PG_CHECK_EXECUTED: '+kind in text
        item = {'kind':kind,'native_exit':code,'executed':completed,'log':str(log),
                'report':str(directory/(kind+'.rpt')),'acceptance':'raw violations require review'}
        checks.append(item); progress()
        return completed

    print('RECOVERY_SOURCE:',source,flush=True)
    print('CURRENT_1109_DESIGN:',bound['design_source'],flush=True)
    print('REUSE_RC_CHECKPOINT:',first,flush=True)
    print('NO_DC_OR_POWER_RERUN; PG rebuilt from saved RC; original failed PG remains untouched',flush=True)
    progress()
    try:
        for phase,limit in PHASES:
            failed = phase
            directory = out/'stages'/phase; directory.mkdir(parents=True)
            lib = directory/'system_1109.nlib'; before = tree(current)
            shutil.copytree(str(current),str(lib))
            if tree(lib) != before: raise ValueError('Checkpoint copy mismatch')
            config = ''.join(scalar(k,v) for k,v in [('Phase',phase),('DesignLib',lib),('RcTlu',rc['tlup']),('RcMap',rc['map'])])
            (directory/'FullConfig.tcl').write_text(config+tlist('RefLibs',refs))
            code,text,log = run_native(out,directory,phase,limit,'ResumeStage.tcl',icc,flag)
            complete = code == 0 and 'FULL_PR_PHASE_COMPLETE: '+phase in text and not operational_errors(text)
            # An interrupted report must not lose a verified, already saved core result.
            core_saved = ('FULL_PR_CORE_SAVED: '+phase in text and (directory/'checkpoint.def').is_file())
            stages.append({'phase':phase,'native_exit':code,'complete':complete,'core_saved':core_saved,'log':str(log),'library':str(lib)})
            if core_saved: current = lib
            progress()
            if not complete:
                print(text[-9000:],flush=True)
                raise ValueError('Phase incomplete; inspect last saved checkpoint: '+phase)
            print('PHASE_COMPLETE:',phase,'LIBRARY:',lib,flush=True)
            if phase == '02_pg':
                failed = 'pg_connectivity'
                if not check('pg_connectivity',1800):
                    raise ValueError('Connectivity command incomplete; PG checkpoint retained')
        final = out/'stages/07_export'
        for name in ('routed.v','routed.sdc','checkpoint.def','qor.rpt','setup.rpt','hold.rpt'):
            if not (final/name).is_file() or not (final/name).stat().st_size:
                raise ValueError('Missing final output: '+name)
        count = routed_nets(final/'checkpoint.def')
        if count < 100: raise ValueError('Missing substantial ordinary signal routing')
        failed = 'final_checks'
        check('pg_connectivity_final',1800)
        check('pg_drc',3600)
        verify(original)
        for p,fingerprint in snapshots.items():
            if tree(Path(p)) != fingerprint: raise ValueError('Original library changed: '+p)
        (out/'OpenRoutedLayout.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')
        save(out/'RecoverySummary.json',{'result':'NEW_1109_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING',
            'source':str(source),'design_source':bound['design_source'],'stages':stages,'checks':checks,
            'original_inputs_unchanged':True,'final_library':str(current),'ordinary_net_route_records':count,
            'acceptance':'Review raw timing, route, connectivity and DRC reports; timeouts remain pending, not pass'})
        print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
        print('CHECKS_EXECUTED:',sum(c['executed'] for c in checks),'OF',len(checks),flush=True)
        print('RESULT: NEW_1109_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING',flush=True)
    except Exception:
        save(out/'RecoveryFailure.json',{'failed_phase':failed,'last_successful_library':str(current),'stages':stages,'checks':checks})
        raise


if __name__ == '__main__':
    try: main(Path(sys.argv[1]).resolve())
    except Exception as error:
        print('FULL_PR_RECOVERY_ERROR:',error,flush=True); traceback.print_exc()
        print('RESULT: NEW_1109_PR_RECOVERY_INCOMPLETE_RETAIN_CHECKPOINTS',flush=True)
        raise SystemExit(2)
