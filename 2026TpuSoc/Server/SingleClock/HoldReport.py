"""Read-only recovery provenance and outside-cell diff; Python 2.7/3."""
from __future__ import print_function
import json
import math
import os
import sys
from VerifyHoldInputs import COMMIT, MANIFEST, sha, read, recheck


def prepare(previous, work):
    recheck(previous)
    with open(os.path.join(previous, 'inputs.json')) as stream:
        original_inputs = json.load(stream)
    original = original_inputs['original_run']
    if sha(os.path.join(original, 'package_manifest.sha256')) != MANIFEST or original_inputs['source_commit'] != COMMIT:
        raise ValueError('Expected exact single-clock v4 inputs')
    failure = read(os.path.join(previous, 'dc.log'))
    if b'HOLD_REPAIR_ERROR: Outside-SRAM leaf count changed' not in failure:
        raise ValueError('Expected v5 outside-cell-count failure')
    candidate = os.path.join(previous, 'E203TpuBackend', 'E203TpuBackend_hold_candidate.ddc')
    baseline = original_inputs['checkpoint_copy']['path']
    inputs = [dict(path=path, sha256=sha(path)) for path in (baseline, candidate)] + original_inputs['libraries']
    for name in ('StdDb.txt', 'SpDb.txt'):
        with open(os.path.join(work, name), 'wb') as stream:
            stream.write(read(os.path.join(previous, name)))
    for name, path in [('BaselineDdc.txt', baseline), ('CandidateDdc.txt', candidate)]:
        with open(os.path.join(work, name), 'w') as stream:
            stream.write(path+'\n')
    with open(os.path.join(work, 'report_inputs.json'), 'w') as stream:
        json.dump(dict(previous=previous, original_run=original, inputs=inputs), stream, indent=2)
        stream.write('\n')
    print('READ_ONLY_INPUTS_VERIFIED: baseline/candidate DDC fingerprints, original libraries and checkpoint unchanged')


def table(path):
    result = {}
    with open(path) as stream:
        for line in stream:
            key, value = line.rstrip('\r\n').split('\t', 1)
            if key in result:
                raise ValueError('Duplicate snapshot key: '+key)
            result[key] = value
    return result


def differences(before, after):
    result = []
    pseudo = ('**logic_0**', '**logic_1**')
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        kind = 'CHANGED'
        if old is None:
            kind = 'ADDED'
        elif new is None:
            kind = 'REMOVED'
        category = 'REAL_CELL'
        if (old is None or old in pseudo) and (new is None or new in pseudo):
            category = 'PSEUDO_CONSTANT'
        result.append((category, kind, name, old or '-', new or '-'))
    return result


def compare(work):
    with open(os.path.join(work, 'report_inputs.json')) as stream:
        inputs = json.load(stream)
    for entry in inputs['inputs']:
        if sha(entry['path']) != entry['sha256']:
            raise ValueError('Read-only input changed: '+entry['path'])
    before_dir, after_dir = [os.path.join(work, name) for name in ('baseline', 'candidate')]
    before, after = [table(os.path.join(path, 'metrics.tsv')) for path in (before_dir, after_dir)]
    delta = differences(table(os.path.join(before_dir, 'outside_cells.tsv')),
                        table(os.path.join(after_dir, 'outside_cells.tsv')))
    diff_path = os.path.join(work, 'outside_changes.tsv')
    with open(diff_path, 'w') as stream:
        stream.write('category\tkind\tname\tbefore_reference\tafter_reference\n')
        for row in delta:
            stream.write('\t'.join(row)+'\n')
    signatures_equal = read(os.path.join(before_dir, 'timing_signature.txt')) == read(os.path.join(after_dir, 'timing_signature.txt'))
    values = []
    output = []
    for key in ('SETUP_WNS_NS', 'HOLD_WNS_NS', 'SRAM_INPUT_HOLD_WNS_NS', 'AREA'):
        for label, data in [('BEFORE', before), ('AFTER', after)]:
            value = float(data[key])
            if math.isnan(value) or math.isinf(value):
                raise ValueError('Invalid metric: '+key)
            output.append(label+'_'+key+': '+data[key])
            if label == 'AFTER' and key != 'AREA':
                values.append(value)
    real = [row for row in delta if row[0] == 'REAL_CELL']
    constants = [row for row in delta if row[0] == 'PSEUDO_CONSTANT']
    output += ['TIMING_REQUIREMENTS: '+('UNCHANGED' if signatures_equal else 'CHANGED'),
               'OUTSIDE_REAL_CELL_CHANGES: '+str(len(real)),
               'OUTSIDE_PSEUDO_CONSTANT_CHANGES: '+str(len(constants)),
               'CPU_REAL_CELL_CHANGES: '+str(sum(row[2].startswith('Cpu/') for row in real)),
               'TIMING_REPAIR_STATUS: '+('PASS (TT pre-layout)' if signatures_equal and min(values) >= 0 else 'FAIL'),
               'CANDIDATE_REVIEW: '+('PENDING_OUTSIDE_CHANGE_REVIEW' if delta else 'OUTSIDE_REFERENCES_UNCHANGED'),
               'OUTSIDE_CHANGE_DETAILS: '+diff_path,
               'INPUT_DDCS_AND_LIBRARIES: UNCHANGED (hash verified)',
               'NETLIST_EQUIVALENCE: NOT_ESTABLISHED']
    with open(os.path.join(work, 'hold_report_summary.txt'), 'w') as stream:
        stream.write('\n'.join(output)+'\n')
    print('\n'.join(output))
    for row in (real[:8]+constants[:8]):
        print('OUTSIDE_CHANGE: '+' | '.join(row))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--compare':
        compare(sys.argv[2])
    elif len(sys.argv) == 3:
        prepare(os.path.realpath(sys.argv[1]), os.path.realpath(sys.argv[2]))
    else:
        raise SystemExit('Usage: HoldReport.py V5_RECOVERY_DIR NEW_WORK | --compare NEW_WORK')
