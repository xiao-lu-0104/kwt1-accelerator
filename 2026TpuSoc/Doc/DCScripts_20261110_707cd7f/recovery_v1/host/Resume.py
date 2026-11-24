"""Resume only the current 707cd7f baseline, preserving every original input."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile


REV = '707cd7f4a0a4d416d11bac71112980079e0a9d34'
RUN_NAME = 'tpusoc_frontend_20261110_707cd7f_ZKpdeM'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def verify(run, expected_manifest):
    manifest = run / 'MANIFEST.sha256'
    if sha(manifest) != expected_manifest:
        raise ValueError('Original frozen 707cd7f manifest changed')
    paths = [manifest]
    for line in manifest.read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = (run / name).resolve()
        if run.resolve() not in path.parents or not path.is_file() or sha(path) != digest:
            raise ValueError('Original payload changed: ' + name)
        paths.append(path)
    if json.loads((run / 'SourceProvenance.json').read_text())['frontend_revision'] != REV:
        raise ValueError('Original source commit mismatch')
    log = run / 'logs/dc.log'
    text = log.read_text(errors='replace')
    for marker in ('DC_STAGE: baseline_saved', 'DC_STAGE: sram_hold_start'):
        if not re.search('^' + re.escape(marker) + '$', text, re.M):
            raise ValueError('Missing actual native stage: ' + marker)
    wrapper = run / 'dc_attempt/runner.log'
    if 'STAGE_TIMEOUT: accelerator_707cd7f_dc' not in wrapper.read_text(errors='replace'):
        raise ValueError('Original timeout not recorded')
    for suffix in ('ddc', 'v', 'sdc'):
        if (run / ('mapped/candidate.' + suffix)).exists():
            raise ValueError('Candidate already exists; review before selecting an older baseline')
        path = run / ('mapped/baseline.' + suffix)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError('Missing nonempty baseline checkpoint: ' + str(path))
        paths.append(path)
    libraries = []
    ledger = run / 'library_sha256.txt'
    for line in ledger.read_text().splitlines():
        digest, name = line.split(None, 1)
        path = Path(name.strip())
        if not path.is_absolute() or not path.is_file() or sha(path) != digest:
            raise ValueError('Original library fingerprint mismatch: ' + str(path))
        libraries.append(path)
    if len(libraries) != 2 or libraries[1].name != 'RAMSP1024X16_tt_1p10v_1p10v_25c.db':
        raise ValueError('Expected original standard/private library pair')
    paths += libraries + [ledger, log, wrapper]
    for name in ('mapped/baseline_setup.rpt', 'mapped/baseline_hold.rpt', 'mapped/guidance.svf', 'vendor_inputs.json'):
        path = run / name
        if path.is_file():
            paths.append(path)
    return paths, libraries


def main():
    out = Path(sys.argv[1]).resolve()
    config = json.loads((out / 'RecoveryConfig.json').read_text())
    run = Path.home() / 'soc' / RUN_NAME
    if run.resolve() == out:
        raise ValueError('Recovery must have an independent directory')
    paths, libraries = verify(run, config['original_manifest_sha256'])
    originals = {str(p): sha(p) for p in paths}
    (out / 'inputs').mkdir()
    (out / 'mapped').mkdir()
    for suffix in ('ddc', 'v', 'sdc'):
        src = run / ('mapped/baseline.' + suffix)
        dst = out / ('inputs/baseline.' + suffix)
        shutil.copy2(src, dst)
        if sha(dst) != originals[str(src)]:
            raise ValueError('Baseline copy fingerprint mismatch')
    # Keep the possibly interrupted original SVF separate; it is not a completed proof.
    old_svf = run / 'mapped/guidance.svf'
    if old_svf.is_file():
        shutil.copy2(old_svf, out / 'inputs/original_interrupted_guidance.svf')
    record = {'source_commit': REV, 'original_run': str(run), 'original_sha256': originals,
              'baseline_checkpoint_hashes_captured_now': True,
              'claim': 'saved mapped baseline; fresh hold-only recovery, no RTL synthesis or library conversion',
              'limit_seconds': 7200}
    record['new_inputs_sha256'] = {str(p): sha(p) for p in (out / 'inputs').iterdir()}
    (out / 'RecoveryInputs.json').write_text(json.dumps(record, indent=2) + '\n')
    dc = os.environ.get('DC_BIN') or shutil.which('dc_shell')
    if not dc:
        dc = '/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell'
    if not os.access(dc, os.X_OK):
        raise ValueError('DC executable unavailable: ' + dc)
    env = dict(os.environ, TPU_STDCELL_DB=str(libraries[0]), TPU_SRAM_DB=str(libraries[1]),
               TPU_SHARED_TOOLS=str(out / 'tools'), TPU_ASIC_OUT=str(out / 'mapped'),
               TPU_RECOVERY_INPUT=str(out / 'inputs'))
    print('SOURCE_COMMIT:', REV, flush=True)
    print('BASELINE_REUSED:', run / 'mapped/baseline.ddc', flush=True)
    print('SCOPE: read saved baseline, validate reload, hold-only compile, checkpoint before reports', flush=True)
    print('LIMIT_SECONDS: 7200 (upper bound, not runtime estimate)', flush=True)
    code = subprocess.call(['python3', str(out / 'tools/StageWatch.py'), '--label', '707cd7f_hold_recovery',
        '--limit', '7200', '--log', str(out / 'mapped/dc.log'), '--cwd', str(out / 'mapped'),
        '--', dc, '-f', str(out / 'tools/Resume.tcl')], env=env)
    unchanged = all(Path(p).is_file() and sha(Path(p)) == h for p, h in originals.items())
    copies_unchanged = all(Path(p).is_file() and sha(Path(p)) == h for p, h in record['new_inputs_sha256'].items())
    (out / 'SourceUnchanged.json').write_text(json.dumps({'original_unchanged': unchanged,
        'input_copies_unchanged': copies_unchanged, 'native_exit': code}, indent=2) + '\n')
    log = (out / 'mapped/dc.log').read_text(errors='replace')
    complete = code == 0 and 'SHARED_ASIC_REPORTS_COMPLETE:' in log
    complete = complete and not re.search(r'^(Error:|SHARED_ASIC_ERROR:)', log, re.M)
    required = ['candidate.ddc', 'candidate.v', 'candidate.sdc', 'guidance.svf', 'summary.txt',
                'candidate_leaves.tsv', 'outside_before.tsv', 'outside_after.tsv',
                'ReloadBaselineSummary.txt', 'reload_baseline.sdc', 'area.rpt', 'units.rpt',
                'check_design.rpt', 'check_timing.rpt', 'setup.rpt', 'hold.rpt']
    complete = complete and all((out / 'mapped' / n).is_file() and (out / 'mapped' / n).stat().st_size for n in required)
    outputs = {p.relative_to(out).as_posix(): sha(p) for p in (out / 'mapped').iterdir() if p.is_file()}
    (out / 'RecoveryOutputs.json').write_text(json.dumps(outputs, indent=2) + '\n')
    with tarfile.open(str(out / 'RecoveryReports.tar.gz'), 'w:gz') as archive:
        for name in ('RecoveryConfig.json', 'RecoveryInputs.json', 'SourceUnchanged.json',
                     'RecoveryOutputs.json', 'PACKAGE.sha256', 'inputs', 'mapped', 'tools'):
            archive.add(str(out / name), arcname=name)
    print('ORIGINAL_INPUTS_UNCHANGED:', unchanged, flush=True)
    if not unchanged or not copies_unchanged or not complete:
        print('RESULT: NEW_707CD7F_HOLD_RECOVERY_INCOMPLETE_RETAIN_CHECKPOINTS', flush=True)
        print('WORK_DIR:', out, flush=True)
        raise SystemExit(1)
    print((out / 'mapped/summary.txt').read_text(), flush=True)
    for name in ('check_design.rpt', 'check_timing.rpt'):
        print('REPORT_TAIL:', name, flush=True)
        print('\n'.join((out / 'mapped' / name).read_text().splitlines()[-25:]), flush=True)
    print('RESULT: NEW_707CD7F_HOLD_RECOVERY_REPORTS_COMPLETE_REVIEW_PENDING', flush=True)
    print('ACCEPTANCE: review setup/hold/checks/outside changes and equivalence before system DC', flush=True)


if __name__ == '__main__':
    main()
