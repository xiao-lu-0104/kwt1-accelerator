"""Diagnose an unchanged failed run using two fresh, report-only DC sessions (Python 3.6+)."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def verify_manifest(run, expected):
    manifest = run / 'MANIFEST.sha256'
    if sha(manifest) != expected:
        raise ValueError('Original frozen payload manifest mismatch')
    paths = []
    for line in manifest.read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = (run / name).resolve()
        if run.resolve() not in path.parents or not path.is_file() or sha(path) != digest:
            raise ValueError('Original payload changed: ' + name)
        paths.append(path)
    return paths + [manifest]


def leaves(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    result = {row['name']: row for row in rows}
    if len(result) != len(rows) or not rows:
        raise ValueError('Duplicate or empty leaf inventory')
    return result


def difference(before, after):
    result = []
    for name in sorted(set(before) | set(after)):
        a, b = before.get(name), after.get(name)
        if a and b and a['ref'] == b['ref']:
            continue
        result.append({'name': name, 'kind': 'added' if not a else 'removed' if not b else 'ref_changed',
                       'before': a['ref'] if a else '', 'after': b['ref'] if b else '',
                       'region': (a or b)['region']})
    return result


def timing_lines(path):
    return sorted(line.strip() for line in path.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith('#')
                  and not re.match(r'^\s*(set_fix_hold|set_dont_touch)\s', line))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--run', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.run:
        candidates = [args.run.expanduser().resolve()]
    else:
        candidates = []
        for run in (Path.home() / 'soc').glob('tpusoc_refresh_dc_20261109_*'):
            log = run / 'logs/dc.log'
            if log.is_file() and 'SHARED_ASIC_ERROR: Outside-SRAM leaf count changed' in log.read_text(errors='replace'):
                candidates.append(run.resolve())
    if len(candidates) != 1:
        raise ValueError('Expected one failed run, found ' + str(len(candidates)))
    run = candidates[0]
    paths = verify_manifest(run, args.manifest_sha)
    library_paths = []
    for line in (run / 'library_sha256.txt').read_text().splitlines():
        digest, name = line.split(None, 1)
        path = Path(name.strip())
        if not path.is_file() or sha(path) != digest:
            raise ValueError('Library ledger mismatch: ' + str(path))
        library_paths.append(path)
    if len(library_paths) != 2:
        raise ValueError('Expected standard-cell and SRAM library ledger')
    artifacts = [run / 'mapped' / (stem + '.' + ext)
                 for stem in ('baseline', 'candidate') for ext in ('ddc', 'v', 'sdc')]
    artifacts += [run / 'mapped/guidance.svf', run / 'logs/dc.log', run / 'library_sha256.txt']
    paths += library_paths + artifacts
    for path in paths:
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing input: ' + str(path))
    initial = {str(path): sha(path) for path in paths}
    (out / 'Inputs.json').write_text(json.dumps({'run': str(run), 'sha256': initial,
        'note': 'checkpoint/library ledger hashes checked now; no claim of historical checkpoint fingerprints'}, indent=2))
    dc = os.environ.get('DC_BIN') or shutil.which('dc_shell')
    if not dc:
        raise ValueError('dc_shell not found')
    print('ORIGINAL_RUN:', run, flush=True)
    env = dict(os.environ, TPU_STDCELL_DB=str(library_paths[0]), TPU_SRAM_DB=str(library_paths[1]),
               TPU_ORIGINAL_TOOLS=str(run / 'tools'))
    failure = None
    try:
        for stem in ('baseline', 'candidate'):
            directory = out / stem
            directory.mkdir()
            env.update(TPU_REVIEW_OUT=str(directory), TPU_REVIEW_DDC=str(run / 'mapped' / (stem + '.ddc')))
            command = ['python3', str(out / 'StageWatch.py'), '--label', stem, '--limit', '240',
                       '--log', str(directory / 'dc.log'), '--cwd', str(directory), '--', dc, '-f', str(out / 'Review.tcl')]
            result = subprocess.call(command, env=env)
            log = (directory / 'dc.log').read_text(errors='replace')
            if result or 'CHECKPOINT_REVIEW_COMPLETE:' not in log or re.search(r'^(Error:|CHECKPOINT_REVIEW_ERROR:)', log, re.M):
                print(log[-7000:], flush=True)
                raise ValueError(stem + ' report-only session failed')
        before, after = [leaves(out / stem / 'leaves.tsv') for stem in ('baseline', 'candidate')]
        changes = difference(before, after)
        with (out / 'LeafChanges.tsv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=['name', 'kind', 'before', 'after', 'region'], delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(changes)
        outside = [row for row in changes if row['region'] == 'outside']
        summary = {'original_run': str(run), 'baseline_leaves': len(before), 'candidate_leaves': len(after),
                   'outside_sram_changes': len(outside), 'all_changes': len(changes),
                   'outside_examples': outside[:30],
                   'timing_requirements_text_equal': timing_lines(run / 'mapped/baseline.sdc') == timing_lines(run / 'mapped/candidate.sdc'),
                   'acceptance': 'DIAGNOSIS_ONLY; original guard not waived; no synthesis acceptance'}
        (out / 'ReviewSummary.json').write_text(json.dumps(summary, indent=2))
        for stem in ('baseline', 'candidate'):
            print('CHECKPOINT:', stem)
            print((out / stem / 'summary.txt').read_text())
        print('OUTSIDE_SRAM_CHANGES:', len(outside))
        for row in outside[:15]:
            print('DIFF:', row['kind'], row['name'], row['before'], '->', row['after'])
    except Exception as error:
        failure = error
    finally:
        unchanged = all(path.is_file() and sha(path) == initial[str(path)] for path in paths)
        (out / 'SourceUnchanged.json').write_text(json.dumps({'unchanged': unchanged, 'original_run': str(run)}))
        print('ORIGINAL_INPUTS_UNCHANGED:', unchanged, flush=True)
        with tarfile.open(str(out / 'DcReviewReports.tar.gz'), 'w:gz') as archive:
            for path in sorted(out.rglob('*')):
                if path.is_file() and path.name != 'DcReviewReports.tar.gz':
                    archive.add(str(path), arcname=str(path.relative_to(out)), recursive=False)
        if not unchanged:
            raise ValueError('Original inputs changed during review')
    if failure:
        raise failure
    print('RESULT: CHECKPOINT_DIAGNOSIS_COMPLETE_ORIGINAL_POLICY_REVIEW_PENDING')


if __name__ == '__main__':
    main()
