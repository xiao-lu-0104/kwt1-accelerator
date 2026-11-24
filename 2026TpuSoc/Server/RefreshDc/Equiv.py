"""Verify incremental hold netlists without repeating synthesis (Python 3.6+)."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from Review import sha, verify_manifest, leaves, difference, timing_lines


def validate_changes(changes):
    actual = Counter((r['region'], r['kind'], r['before'], r['after']) for r in changes)
    expected = Counter({
        ('outside', 'added', '', 'BUFV32_12TR40'): 1,
        ('outside', 'added', '', 'BUFV32RD_12TR40'): 50,
        ('outside', 'added', '', 'BUFV32RQ_12TR40'): 10,
        ('sram', 'added', '', 'BUFV24RQ_12TR40'): 8,
        ('sram', 'added', '', 'BUFV32_12TR40'): 16,
        ('sram', 'added', '', 'BUFV32RQ_12TR40'): 144,
        ('sram', 'added', '', 'DEL4V0_12TR40'): 128})
    if actual != expected:
        raise ValueError('Incremental changes differ from the reviewed 357 added buffers/delay cells')


def accepted(code, unchanged, status, log):
    return (code == 0 and unchanged and status.get('VERIFY_RETURN') == ['1']
        and status.get('MATCH_RETURN') == ['1']
        and status.get('RESULT') == ['HOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING']
        and not re.search(r'^Error:', log, re.M))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--manifest-sha', required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    choices = []
    for path in (Path.home() / 'soc').glob('tpusoc_dc_review_20261109_*'):
        summary = path / 'ReviewSummary.json'
        unchanged = path / 'SourceUnchanged.json'
        if summary.is_file() and unchanged.is_file() and json.loads(unchanged.read_text()).get('unchanged') is True:
            data = json.loads(summary.read_text())
            if data.get('baseline_leaves') == 137490 and data.get('candidate_leaves') == 137847:
                choices.append(path)
    if len(choices) != 1:
        raise ValueError('Expected one successful matching checkpoint review, found ' + str(len(choices)))
    review = choices[0]
    record = json.loads((review / 'Inputs.json').read_text())
    run = Path(record['run']).resolve()
    for name, digest in record['sha256'].items():
        if sha(Path(name)) != digest:
            raise ValueError('Reviewed original input changed: ' + name)
    verify_manifest(run, args.manifest_sha)
    with (review / 'LeafChanges.tsv').open() as stream:
        import csv
        changes = list(csv.DictReader(stream, delimiter='\t'))
    baseline = leaves(review / 'baseline/leaves.tsv')
    candidate = leaves(review / 'candidate/leaves.tsv')
    if len(baseline) != 137490 or len(candidate) != 137847:
        raise ValueError('Leaf inventories do not match reviewed checkpoint counts')
    recomputed = difference(baseline, candidate)
    if changes != recomputed:
        raise ValueError('Leaf inventory and recorded difference disagree')
    validate_changes(changes)
    if timing_lines(run / 'mapped/baseline.sdc') != timing_lines(run / 'mapped/candidate.sdc'):
        raise ValueError('Timing requirements changed')
    libraries = []
    for line in (run / 'library_sha256.txt').read_text().splitlines():
        digest, name = line.split(None, 1)
        path = Path(name.strip())
        if sha(path) != digest:
            raise ValueError('Library changed')
        libraries.append(path)
    if len(libraries) != 2:
        raise ValueError('Expected two reviewed technology libraries')
    tracked = [Path(name) for name in record['sha256']]
    tracked += [review / name for name in ('Inputs.json', 'ReviewSummary.json', 'LeafChanges.tsv',
        'baseline/leaves.tsv', 'candidate/leaves.tsv', 'SourceUnchanged.json')]
    initial = {str(p): sha(p) for p in tracked}
    (out / 'EquivInputs.json').write_text(json.dumps({'run': str(run), 'review': str(review), 'sha256': initial}, indent=2))
    fm = os.environ.get('FM_BIN') or shutil.which('fm_shell')
    if not fm:
        known = Path.home() / 'soc/tpusoc_final_preflight_20261108_sCgoD1/BackendPreflight.json'
        if known.is_file():
            fm = json.loads(known.read_text()).get('tools', {}).get('fm_shell', {}).get('executable')
    if not fm or not Path(fm).is_file() or not os.access(fm, os.X_OK):
        raise ValueError('fm_shell executable unavailable; set FM_BIN explicitly')
    env = dict(os.environ, TPU_STDCELL_DB=str(libraries[0]), TPU_SRAM_DB=str(libraries[1]),
        TPU_BASELINE_NETLIST=str(run / 'mapped/baseline.v'), TPU_CANDIDATE_NETLIST=str(run / 'mapped/candidate.v'))
    print('ORIGINAL_RUN:', run, flush=True)
    print('MODE: exact baseline versus candidate netlists; no synthesis, no SVF or added state assumptions', flush=True)
    code = subprocess.call(['python3', str(out / 'StageWatch.py'), '--label', 'hold_netlist_equivalence',
        '--limit', '900', '--log', str(out / 'fm.log'), '--cwd', str(out), '--', fm, '-f', str(out / 'Equiv.tcl')], env=env)
    unchanged = all(p.is_file() and sha(p) == initial[str(p)] for p in tracked)
    (out / 'SourceUnchanged.json').write_text(json.dumps({'unchanged': unchanged}))
    log = (out / 'fm.log').read_text(errors='replace')
    status = {}
    if (out / 'EquivStatus.tsv').is_file():
        for line in (out / 'EquivStatus.tsv').read_text().splitlines():
            key, value = line.split('\t', 1)
            status.setdefault(key, []).append(value)
    success = accepted(code, unchanged, status, log)
    summary = {'original_run': str(run), 'review': str(review), 'native_exit': code, 'status': status,
        'input_unchanged': unchanged, 'result': 'HOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING' if success else 'FAILED_OR_INCONCLUSIVE',
        'scope': 'baseline versus hold candidate only; not RTL equivalence or SRAM internal proof'}
    (out / 'EquivSummary.json').write_text(json.dumps(summary, indent=2))
    with tarfile.open(str(out / 'HoldEquivReports.tar.gz'), 'w:gz') as archive:
        for path in sorted(out.iterdir()):
            if path.is_file() and path.name != 'HoldEquivReports.tar.gz' and path.suffix != '.fss':
                archive.add(str(path), arcname=path.name, recursive=False)
    print('MATCH_RETURN:', status.get('MATCH_RETURN', ['NOT_REACHED'])[-1])
    print('VERIFY_RETURN:', status.get('VERIFY_RETURN', ['NOT_REACHED'])[-1])
    print('ORIGINAL_INPUTS_UNCHANGED:', unchanged)
    for side in ('r', 'i'):
        path = out / ('black_boxes_' + side + '.rpt')
        if path.is_file():
            print('BLACKBOX_REPORT:', side)
            lines = path.read_text(errors='replace').splitlines()
            print('\n'.join(lines if len(lines) <= 24 else lines[:16] + ['... full report retained ...'] + lines[-8:]))
    print('RESULT:', summary['result'])
    if not success:
        print(log[-6500:])
        raise SystemExit(2)


if __name__ == '__main__':
    main()
