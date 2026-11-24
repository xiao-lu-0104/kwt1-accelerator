"""Read server tools, own processes and old PR state; write only in this run."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def main():
    out = Path(sys.argv[1]).resolve()
    record = {'source_commit': '707cd7f4a0a4d416d11bac71112980079e0a9d34',
              'mode': 'READ_ONLY_OLD_RUNS', 'tools': {}, 'old_pr': [], 'private_db_candidates': []}
    for name, fallback in [('dc_shell', '/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell'),
                           ('icc2_shell', '/eda/synopsys/icc2/icc2_2022.03-SP2-1/bin/icc2_shell')]:
        path = shutil.which(name) or fallback
        record['tools'][name] = {'path': path, 'executable': os.access(path, os.X_OK)}
    ps = subprocess.check_output(['ps', '-u', str(os.getuid()), '-o', 'pid,ppid,etime,pcpu,pmem,args'],
                                  universal_newlines=True)
    record['processes'] = ps
    record['memory'] = subprocess.check_output(['free', '-m'], universal_newlines=True)
    home = Path.home() / 'soc'
    # Never open a design nlib, issue a tool command, or signal another process.
    for pattern in ('tpusoc_full_pr_20261109_*', 'tpusoc_pr_prepare_20261109_*'):
        for directory in sorted(home.glob(pattern)):
            entry = {'directory': str(directory), 'tails': {}}
            for name in ('runner.log', 'progress.json', 'failure.json', 'OpenLastCheckpoint.tcl'):
                path = directory / name
                if path.is_file():
                    with path.open('rb') as stream:
                        stream.seek(max(0, path.stat().st_size - 6000))
                        entry['tails'][name] = stream.read().decode('utf-8', errors='replace')
            record['old_pr'].append(entry)
    # A ledger alone is not enough: tie reuse to the old pinned source and vendor evidence.
    for directory in sorted(home.glob('tpusoc_refresh_dc_20261109_*')):
        try:
            provenance = json.loads((directory / 'SourceProvenance.json').read_text())
            vendor = json.loads((directory / 'vendor_inputs.json').read_text())
            if provenance.get('frontend_revision') != 'c03eb048481b7d271dba54e518092c2eb9aa528f':
                continue
            expected = {'verilog/RAMSP1024X16.v': '81b55d87d5e6821d44037d6f0290ec89c9edb9582eb1932957f181aefc300d51',
                        'lib/RAMSP1024X16_tt_1p10v_1p10v_25c.lib': '7cf092257dfe18f32affee2d1a071b198b7cc68cb50b5bc71b0fdc98a79cfdb1'}
            if vendor.get('inputs_sha256') != expected:
                continue
            entries = []
            for line in (directory / 'library_sha256.txt').read_text().splitlines():
                digest, name = line.split(None, 1)
                path = Path(name.strip())
                if not path.is_absolute() or not path.is_file() or sha(path) != digest:
                    raise ValueError('Historical ledger mismatch: ' + name)
                entries.append((path, digest))
            dbs = [(p, h) for p, h in entries if p.name == 'RAMSP1024X16_tt_1p10v_1p10v_25c.db']
            if len(entries) == 2 and len(dbs) == 1:
                record['private_db_candidates'].append({'path': str(dbs[0][0]), 'sha256': dbs[0][1],
                    'old_run': str(directory), 'ledger_sha256': sha(directory / 'library_sha256.txt')})
        except (OSError, ValueError, KeyError) as error:
            record.setdefault('reuse_rejections', []).append({'directory': str(directory), 'reason': str(error)})
    (out / 'ServerProbe.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2), flush=True)
    print('PROBE_RESULT: SERVER_STATE_RECORDED_1109_UNTOUCHED')


if __name__ == '__main__':
    main()
