"""Fresh PG and basic routed implementation of 707cd7f, retaining all violations."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time

from PrHelpers import scalar, sha, tlist, verify
from PgFlow import choose_source
from ContinuePr import parse_connectivity, parse_drc
from RcHelpers import routed_nets

HERE = Path(__file__).resolve().parent
REV = '707cd7f4a0a4d416d11bac71112980079e0a9d34'
ORIGIN = Path('/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L')
PHASES = [('01_rc', 600), ('02_pg_basic', 1200), ('04_build_clock', 1800),
          ('04_route_clock', 1800), ('05_route', 3600), ('07_export', 600)]
CHECKS = [('connectivity', 180), ('drc', 600)]


def save(path, data):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    os.replace(str(temporary), str(path))


def snapshot(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Unexpected library symlink: '+str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    if not result:
        raise ValueError('Empty library: '+str(root))
    return result


def prepare(out):
    cfg = json.loads((ORIGIN/'Config.json').read_text())
    source, summary = choose_source(Path.home()/'soc', cfg['initial_package_sha256'])
    inputs = json.loads((source/'NewPrInputs.json').read_text())
    if inputs['source_commit'] != REV or sha(source/'inputs/candidate.v') != summary['design_netlist_sha256']:
        raise ValueError('Unexpected frontend or mapped netlist')
    if sha(source/'inputs/candidate.sdc') != inputs['design_sdc_sha256']:
        raise ValueError('Source SDC changed')
    verify(inputs['inputs'])
    original = dict(inputs['inputs'])
    files = out/'inputs'
    files.mkdir(exist_ok=True)
    for name in ('NewPrInputs.json', 'NewPrSummary.json', 'inputs/candidate.v', 'inputs/candidate.sdc',
                 'design/PinPlan.json', 'design/IoValidation.json', 'design/PortTerminalGeometry.tsv'):
        path = source/name
        original[str(path)] = sha(path)
        dest = files/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(dest))
    # These files identify the audited technology, grouped IO and original macro geometry.
    config = (ORIGIN/'stages/01_rc/ContinueConfig.tcl').read_text()
    variables = {}
    old_ledger = json.loads((ORIGIN/'ContinueInputs.json').read_text())['original_files']
    for key in ('BaselineLeaves', 'BaselineMacros', 'BaselineIo', 'RcTlu', 'RcMap'):
        values = re.findall(r'^set '+key+r' \{([^}]+)\}$', config, re.M)
        if len(values) != 1:
            raise ValueError('Missing audited configuration '+key)
        path = Path(values[0])
        digest = sha(path)
        if str(path) in old_ledger and old_ledger[str(path)] != digest:
            raise ValueError('Audited configuration changed: '+str(path))
        original[str(path)] = digest
        dest = files/(key+'_'+path.name)
        shutil.copy2(str(path), str(dest))
        variables[key] = str(dest)
    if sha(variables['BaselineIo']) != sha(source/'design/PortTerminalGeometry.tsv'):
        raise ValueError('IO baseline does not match current grouped IO')
    variables['ExpectedPeriod'] = str(inputs['expected_serialized_period_ns'])
    refs = []
    libraries = {}
    for label in ('rvt', 'private', 'shared'):
        path = source/('library_'+label)/(label+'.ndm')
        expected = [value for name, value in inputs['reference_snapshots'].items()
                    if Path(name).name == label+'.ndm']
        before = snapshot(path)
        if expected != [before]:
            raise ValueError('Reference fingerprint changed: '+label)
        dest = out/('library_'+label)/(label+'.ndm')
        dest.parent.mkdir(exist_ok=True)
        if not dest.exists():
            shutil.copytree(str(path), str(dest))
        if snapshot(dest) != before:
            raise ValueError('Reference copy differs')
        refs.append(str(dest))
        libraries[str(path)] = before
    library = source/'design/system_707cd7f.nlib'
    libraries[str(library)] = snapshot(library)
    physical_path = Path.home()/'soc/tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json'
    physical = json.loads(physical_path.read_text())
    original[str(physical_path)] = sha(physical_path)
    record = {'source_commit': REV, 'source_run': str(source), 'source_library': str(library),
              'source_netlist_sha256': summary['design_netlist_sha256'], 'variables': variables,
              'reference_libraries': refs, 'original_files': original, 'original_libraries': libraries,
              'icc2': physical['icc2'], 'icc2_flag': physical['icc2_flag'],
              'target_seconds': 10800, 'mesh_pitch_um': 84,
              'io': 'retain verified grouped IO coordinates and bus order',
              'acceptance': 'command execution, saved clocks and routed signal geometry; violations reported',
              'omitted_optimization': ['full place_opt', 'clock_opt final_opto', 'standalone route_opt'],
              'timing_constraints': 'original 150 MHz budgets retained',
              'detail_route_iterations': '3 if supported by installed route_auto',
              'budget_behavior': 'advisory; never kill an unsaved stage at the target time'}
    save(out/'FastPrInputs.json', record)
    return record


def run_stage(out, record, label, action, source, budget):
    stage = out/'stages'/label
    attempt = 0
    while stage.exists():
        attempt += 1
        stage = out/'stages'/(label+'_retry'+str(attempt))
    stage.mkdir(parents=True)
    library = stage/'system_707cd7f.nlib'
    before = snapshot(source)
    shutil.copytree(str(source), str(library))
    if snapshot(library) != before or snapshot(source) != before:
        raise ValueError('Input library changed while copying')
    config = tlist('RefLibs', record['reference_libraries'])
    config += ''.join(scalar(key, value) for key, value in record['variables'].items())
    config += scalar('DesignLib', library)+scalar('Action', action)
    (stage/'ContinueConfig.tcl').write_text(config)
    log_path = stage/'native.log'
    started = time.monotonic()
    print('RUN: '+label+' budget_seconds='+str(budget)+' log='+str(log_path), flush=True)
    with log_path.open('x') as log:
        process = subprocess.Popen([record['icc2'], record['icc2_flag'], str(HERE/'FastEngineeringPr.tcl')],
                                   cwd=str(stage), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        save(stage/'NativeProcess.json', {'pid': process.pid, 'stage': label, 'budget_seconds': budget})
        while True:
            try:
                code = process.wait(timeout=60)
                break
            except subprocess.TimeoutExpired:
                elapsed = int(time.monotonic()-started)
                event = 'STAGE_RUNNING' if elapsed < budget else 'STAGE_BUDGET_EXCEEDED_CONTINUING'
                print(event+': '+label+' elapsed_seconds='+str(elapsed)+' native_pid='+str(process.pid), flush=True)
    text = log_path.read_text(errors='replace')
    result = {'stage': label, 'action': action, 'native_exit': code,
              'elapsed_seconds': int(time.monotonic()-started), 'directory': str(stage),
              'library': str(library), 'log': str(log_path),
              'core_saved': 'CONTINUE_CORE_SAVED: '+action in text,
              'complete': code == 0 and 'CONTINUE_PHASE_COMPLETE: '+action in text}
    save(stage/'ActionResult.json', result)
    print('STAGE_FINISHED: '+label+' exit='+str(code)+' elapsed_seconds='+str(result['elapsed_seconds']), flush=True)
    if not result['complete']:
        print(text[-7000:], flush=True)
    return result


def write_progress(out, current, stages):
    save(out/'FastPrProgress.json', {'last_successful_library': str(current), 'stages': stages})
    (out/'OpenLastCheckpoint.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')


def report(out, record, current, stages, checks, elapsed):
    export = next(Path(stage['directory']) for stage in stages if stage['stage'] == '07_export' and stage['complete'])
    for name in ('checkpoint.def', 'routed.v', 'routed.sdc', 'setup.rpt', 'hold.rpt', 'route_check.rpt'):
        if not (export/name).is_file() or not (export/name).stat().st_size:
            raise ValueError('Missing required export '+name)
    routes = routed_nets(export/'checkpoint.def')
    if routes < 100:
        raise ValueError('Insufficient evidence of ordinary signal routing')
    verify(record['original_files'])
    for name, expected in record['original_libraries'].items():
        if snapshot(Path(name)) != expected:
            raise ValueError('Source library changed: '+name)
    timing = {}
    for kind, filename in (('setup', 'setup.rpt'), ('hold', 'hold.rpt')):
        text = (export/filename).read_text(errors='replace')
        values = re.findall(r'slack\s+\((?:MET|VIOLATED)\)\s+(-?\d+(?:\.\d+)?)', text)
        timing[kind] = {'recognized': bool(values), 'worst_reported_slack_ns': min(map(float, values)) if values else None,
                        'report': str(export/filename)}
    route_text = (export/'route_check.rpt').read_text(errors='replace')
    drcs = re.findall(r'Total number of DRCs\s*[:=]\s*(\d+)', route_text)
    explicit_opens = re.findall(r'Total number of open nets\s*[:=]\s*(\d+)|^\s*(\d+) open nets', route_text, re.M)
    route_check = {'reported_drcs': int(drcs[-1]) if drcs else None,
                   'reported_open_nets': int(next(value for value in explicit_opens[-1] if value)) if explicit_opens else None,
                   'report': str(export/'route_check.rpt')}
    summary = {'result': 'NEW_707CD7F_BASIC_PR_EXECUTED_VIOLATIONS_RETAINED', 'source_commit': REV,
               'final_library': str(current), 'export_directory': str(export), 'stages': stages,
               'ordinary_net_route_records': routes, 'checks': checks, 'timing': timing,
               'signal_route_check': route_check, 'elapsed_seconds': elapsed,
               'original_inputs_unchanged': True, 'omitted_optimization': record['omitted_optimization'],
               'acceptance': 'basic placement, fresh PG, clock build/route, signal route and export executed',
               'limitations': 'PG/timing/route violations retained; not manufacturing signoff; GDS optional/unmerged'}
    save(out/'FastPrSummary.json', summary)
    (out/'OpenRoutedLayout.tcl').write_text('open_lib {'+str(current)+'}\nopen_block e203_cpu_top\nstart_gui\n')
    lines = ['# 707cd7f basic physical implementation', '',
             'Source commit '+REV, '', 'Original grouped IO retained. Fresh PG pitch 84 um.', '',
             'Full place_opt, CTS final_opto and standalone route_opt omitted for the delivery schedule.', '',
             'Original 150 MHz timing constraints retained. Violations are reported without a zero-violation acceptance gate.', '',
             '| Stage | Native exit | Seconds | Saved |', '|---|---:|---:|---|']
    for stage in stages:
        lines.append('| '+stage['stage']+' | '+str(stage['native_exit'])+' | '+str(stage['elapsed_seconds'])+' | '+str(stage['core_saved'])+' |')
    lines += ['', 'Ordinary signal route records '+str(routes), '',
              'Final reports and DEF are in '+str(export), '',
              'Timing and signal route checks', '', '```json', json.dumps({'timing': timing, 'signal_route_check': route_check}, indent=2), '```', '',
              'PG checks', '', '```json', json.dumps(checks, indent=2), '```', '',
              'Timing and signal-route reports require review. Optional unmerged GDS excludes a verified full-cell stream merge.']
    (out/'ImplementationReport.md').write_text('\n'.join(lines)+'\n')
    print('RESULT: '+summary['result'], flush=True)
    print('OPEN_GUI: '+record['icc2']+' -file '+str(out/'OpenRoutedLayout.tcl'), flush=True)


def execute(out):
    if (out/'FastPrSummary.json').exists():
        raise ValueError('This run already exported a layout; use OpenRoutedLayout.tcl')
    timing_file = out/'RunTiming.json'
    if not timing_file.exists():
        save(timing_file, {'first_start_epoch': time.time()})
    record = json.loads((out/'FastPrInputs.json').read_text()) if (out/'FastPrInputs.json').exists() else prepare(out)
    verify(record['original_files'])
    stages = []
    current = Path(record['source_library'])
    if (out/'FastPrProgress.json').exists():
        previous = json.loads((out/'FastPrProgress.json').read_text())
        stages = previous['stages']
        current = Path(previous['last_successful_library'])
    print('SOURCE_COMMIT: '+REV, flush=True)
    print('SOURCE_INITIAL_LAYOUT: '+record['source_run'], flush=True)
    print('MODE: fresh sparse PG; split CTS; bounded routing effort; violations retained', flush=True)
    print('TARGET_SECONDS: 10800; advisory budgets preserve running native stages', flush=True)
    for action, budget in PHASES:
        completed = [stage for stage in stages if stage['stage'] == action and stage['complete']]
        if completed:
            continue
        result = run_stage(out, record, action, action, current, budget)
        stages.append(result)
        if result['complete']:
            current = Path(result['library'])
        write_progress(out, current, stages)
        if not result['complete']:
            raise ValueError('Native stage failed: '+action+'; saved previous stage retained')
        print('PHASE_COMPLETE: '+action, flush=True)
    checks = {}
    for action, budget in CHECKS:
        try:
            result = run_stage(out, record, 'check_'+action, action, current, budget)
            path = Path(result['directory'])/(action+'.rpt')
            parser = parse_connectivity if action == 'connectivity' else parse_drc
            data = parser(path.read_text(errors='replace')) if path.is_file() else {'known': False}
            data.update(executed=result['complete'], report=str(path))
            if not result['complete']:
                data['clean'] = False
            checks[action] = data
        except Exception as error:
            checks[action] = {'executed': False, 'known': False, 'clean': False, 'error': str(error)}
        save(out/'FastPrChecks.json', checks)
        print('CHECK_RESULT: '+action+' '+json.dumps(checks[action]), flush=True)
    elapsed = int(time.time()-json.loads(timing_file.read_text())['first_start_epoch'])
    report(out, record, current, stages, checks, elapsed)
    with tarfile.open(str(out/'FastPrReports.tar.gz'), 'w:gz') as archive:
        for path in sorted(out.rglob('*')):
            rel = path.relative_to(out)
            if any(part.endswith(('.nlib', '.ndm')) for part in rel.parts):
                continue
            if path.is_file() and path.name not in ('FastPrReports.tar.gz', 'runner.log', 'payload.tar.gz'):
                archive.add(str(path), arcname=rel.as_posix())


def main(out):
    with (out/'FastPr.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('work_directory', type=Path)
    args = parser.parse_args()
    try:
        main(args.work_directory.resolve())
    except Exception as error:
        import traceback
        print('FAST_PR_ERROR: '+str(error), flush=True)
        traceback.print_exc()
        print('RESULT: NEW_707CD7F_BASIC_PR_INCOMPLETE_CHECKPOINTS_RETAINED', flush=True)
        raise SystemExit(2)
