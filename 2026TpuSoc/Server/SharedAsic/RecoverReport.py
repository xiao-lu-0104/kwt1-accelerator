"""Read-only provenance checks and complete baseline/candidate difference reporting."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from Verify import verify

BUNDLE_SHA = 'baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(path):
    result = {}
    for line in path.read_text().splitlines():
        key, value = line.split('\t', 1)
        if key in result:
            raise ValueError('Duplicate snapshot key: ' + key)
        result[key] = value
    return result


def differences(before, after):
    result = []
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        category = 'PSEUDO_CONSTANT' if all(value in (None, '**logic_0**', '**logic_1**')
                                            for value in (old, new)) else 'REAL_CELL'
        kind = 'ADDED' if old is None else 'REMOVED' if new is None else 'CHANGED'
        scope = 'SRAM' if name.startswith('Tpu/Core/Sram/') else 'OUTSIDE'
        result.append((scope, category, kind, name, old or '-', new or '-'))
    return result


def prepare(previous, out, tools_sha):
    if 'SHARED_ASIC_ERROR: Outside-SRAM leaf count changed' not in (previous / 'logs/dc.log').read_text():
        raise ValueError('Expected shared ASIC outside-SRAM protection failure')
    manifest = previous / 'tools/MANIFEST.sha256'
    if sha(manifest) != tools_sha:
        raise ValueError('Expected exact shared ASIC v2 tools')
    inputs = []
    for line in manifest.read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = previous / 'tools' / name
        if sha(path) != expected:
            raise ValueError('Original tool changed: ' + name)
        inputs.append(path)
    evidence_path = previous / 'source/Evidence.json'
    evidence = json.loads(evidence_path.read_text())
    if evidence['bundle_manifest_sha256'] != BUNDLE_SHA or evidence['top'] != 'e203_subsys_nice_core':
        raise ValueError('Unexpected source association')
    bundle, design, _ = verify(Path(evidence['functional_run']), BUNDLE_SHA)
    original_sources = {path.name: path for path in design}
    original_sources['SpFoundry.sv'] = bundle / 'Server/Backend/SpFoundry.sv'
    for name, expected in evidence['source_sha256'].items():
        path = previous / 'source' / name
        if sha(path) != expected or sha(original_sources[name]) != expected:
            raise ValueError('Synthesis source differs from tested source: ' + name)
        inputs.append(path)
    libraries = []
    for line in (previous / 'library_sha256.txt').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = Path(name)
        if sha(path) != expected:
            raise ValueError('Library changed: ' + name)
        libraries.append(path)
    sp_db = previous / 'sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db'
    if len(libraries) != 2 or libraries[1] != sp_db:
        raise ValueError('Expected original standard-cell and private SRAM DBs')
    inputs += libraries + [manifest, evidence_path, previous / 'library_sha256.txt']
    for mode in ('baseline', 'candidate'):
        for suffix in ('ddc', 'v', 'sdc'):
            path = previous / 'mapped' / (mode + '.' + suffix)
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('Missing saved checkpoint: ' + str(path))
            inputs.append(path)
        (out / (mode + '_ddc.txt')).write_text(str(previous / 'mapped' / (mode + '.ddc')) + '\n')
    (out / 'StdDb.txt').write_text(str(libraries[0]) + '\n')
    (out / 'SpDb.txt').write_text(str(libraries[1]) + '\n')
    record = {'previous': str(previous), 'inputs': {str(path): sha(path) for path in inputs},
              'note': 'DDC hashes captured at recovery start; source/library provenance independently verified'}
    (out / 'ReportInputs.json').write_text(json.dumps(record, indent=2) + '\n')
    print('RECOVERY_INPUTS_VERIFIED: exact v2 tools, tested sources, original libraries and saved checkpoints')


def recheck(out):
    record = json.loads((out / 'ReportInputs.json').read_text())
    for name, expected in record['inputs'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Read-only input changed: ' + name)


def compare(out):
    recheck(out)
    before, after = [table(out / mode / 'metrics.tsv') for mode in ('baseline', 'candidate')]
    delta = differences(table(out / 'baseline/cells.tsv'), table(out / 'candidate/cells.tsv'))
    detail = out / 'cell_changes.tsv'
    detail.write_text('scope\tcategory\tkind\tname\tbefore_reference\tafter_reference\n'
                      + ''.join('\t'.join(row) + '\n' for row in delta))
    equal = ((out / 'baseline/timing_signature.txt').read_bytes()
             == (out / 'candidate/timing_signature.txt').read_bytes())
    summary = []
    timed = []
    for key in ('SETUP_WNS_NS', 'HOLD_WNS_NS', 'SRAM_INPUT_HOLD_WNS_NS', 'AREA', 'SRAM_AREA'):
        for label, data in [('BEFORE', before), ('AFTER', after)]:
            value = float(data[key])
            if not math.isfinite(value):
                raise ValueError('Nonfinite metric: ' + key)
            summary.append(label + '_' + key + ': ' + data[key])
            if label == 'AFTER' and key.endswith('WNS_NS'):
                timed.append(value)
    outside_real = [row for row in delta if row[:2] == ('OUTSIDE', 'REAL_CELL')]
    outside_pseudo = [row for row in delta if row[:2] == ('OUTSIDE', 'PSEUDO_CONSTANT')]
    summary += ['TIMING_REQUIREMENTS: ' + ('UNCHANGED' if equal else 'CHANGED'),
                'TIMING_STATUS: ' + ('PASS_TT_PRELAYOUT' if equal and min(timed) >= 0 else 'FAIL'),
                'OUTSIDE_REAL_CELL_CHANGES: ' + str(len(outside_real)),
                'OUTSIDE_PSEUDO_CONSTANT_CHANGES: ' + str(len(outside_pseudo)),
                'SRAM_CELL_CHANGES: ' + str(sum(row[0] == 'SRAM' for row in delta)),
                'SCOPE_REVIEW: ' + ('REQUIRED' if outside_real or outside_pseudo else 'REFERENCES_UNCHANGED'),
                'CELL_CHANGE_DETAILS: ' + str(detail),
                'CHANGED_CELL_CONNECTIONS: ' + str(out / 'candidate/changed_connections.tsv'),
                'INPUT_CHECKPOINTS_AND_LIBRARIES: UNCHANGED_HASH_VERIFIED',
                'NETLIST_EQUIVALENCE: NOT_ESTABLISHED',
                'POWER: PENDING_ACTIVITY_ANNOTATION',
                'ACCEPTANCE: PENDING_SCOPE_CHECK_DESIGN_AND_TIMING_REVIEW']
    (out / 'summary.txt').write_text('\n'.join(summary) + '\n')
    print('\n'.join(summary))
    for row in (outside_real + outside_pseudo)[:24]:
        print('OUTSIDE_CHANGE: ' + ' | '.join(row))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tools-sha')
    parser.add_argument('--compare', action='store_true')
    args = parser.parse_args()
    if args.compare:
        compare(args.out)
        return
    if args.previous:
        prepare(args.previous.resolve(), args.out, args.tools_sha)
        return
    runs = sorted((Path.home() / 'soc').glob('tpusoc_shared_asic_20261105_*'),
                  key=lambda path: path.stat().st_mtime, reverse=True)
    for previous in runs:
        try:
            prepare(previous, args.out, args.tools_sha)
            return
        except (OSError, KeyError, ValueError) as error:
            print('SKIP:', previous.name, str(error))
    raise ValueError('No matching saved v2 outside-SRAM failure found')


if __name__ == '__main__':
    main()
