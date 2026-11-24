"""Print bounded evidence from a completed object audit; run no EDA tools."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


def table(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def show(root):
    record = json.loads((root / 'ObjectAuditInputs.json').read_text())
    for filename, digest in record['inputs'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen input changed: ' + filename)
    print('WORK_DIR:', root)
    summary = json.loads((root / 'ObjectAuditSummary.json').read_text())
    for task in ('ff1', 'encoder'):
        case = root / task
        data = summary[task]
        print('COUNTS:', task, json.dumps({k: data[k] for k in (
            'statuses', 'unknown_requests', 'unknown_net_no_direct_loads',
            'unknown_net_with_connections')}, sort_keys=True))
        rows = table(case / 'object_connections.tsv')
        unknown = {r['id']: r for r in rows if 'TX_NONZERO' in r['reason']}
        leaves = Counter()
        examples = []
        for row in table(case / 'connection_details.tsv'):
            if row['id'] not in unknown or row['hierarchical'].lower() not in ('false', '0'):
                continue
            if row['direction'] not in ('in', 'inout') or row['reference'] == '<TOP_PORT>':
                continue
            leaves[row['reference']] += 1
            examples.append((row['object'], row['neighbor'], row['reference']))
        print('X_LEAF_LOAD_PIN_COUNTS:', task, json.dumps(leaves.most_common(8)))
        print('X_LEAF_LOAD_NET_COUNT:', task, len({x[0] for x in examples}))
        # One example per source block, bounded independently of query order.
        seen = set()
        for obj, pin, ref in examples:
            block = '/'.join(obj.split('/')[:-1])
            if block in seen:
                continue
            seen.add(block)
            print('X_LEAF_EXAMPLE:', task, obj, '->', pin, ref)
            if len(seen) == 3:
                break
        clocks = [r for r in rows if 'CLOCK_SOURCE_REVIEW' in r['reason']]
        for row in clocks[:4]:
            values = []
            for suffix in ('toggle', 'probability'):
                path = case / ('clock_' + row['id'] + '_' + suffix + '.txt')
                if path.exists():
                    value = path.read_text(errors='replace').strip()
                elif Path(str(path) + '.error.txt').exists():
                    value = 'ERROR ' + Path(str(path) + '.error.txt').read_text(errors='replace')
                else:
                    value = 'NOT_AVAILABLE'
                values.append(suffix + '=' + ' '.join(value.split())[:180])
            print('CLOCK_QUERY:', task, row['name'], '; '.join(values))
        path = case / 'activity_detail.rpt.error.txt'
        if path.exists():
            print('ACTIVITY_REPORT_ERROR:', task, ' '.join(path.read_text(errors='replace').split())[:180])
    print('RESULT: COMPACT_OBJECT_EVIDENCE_COMPLETE; X acceptance and system power remain pending')


def main():
    choices = sorted((Path.home() / 'soc').glob('tpusoc_activity_objects_20261106_*'),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    root = next((p for p in choices if (p / 'ObjectAuditSummary.json').exists()
                 and 'RESULT: ACTIVITY_OBJECT_AUDIT_COMPLETE' in
                 (p / 'runner.log').read_text(errors='replace')), None)
    if root is None:
        raise ValueError('No completed object audit found')
    show(root)


if __name__ == '__main__':
    main()
