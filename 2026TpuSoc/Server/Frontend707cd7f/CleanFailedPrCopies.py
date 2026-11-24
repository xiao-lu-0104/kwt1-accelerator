"""Remove only two verified, unsaved timeout library copies. Default is preview."""
import json
import os
from pathlib import Path
import shutil
import sys

ORIGIN = Path('/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L')
LIGHT = Path('/tmp/tpusoc_pr_light_707cd7f_PhN4TK')
ACTIVE = Path('/tmp/tpusoc_cts_resume_707cd7f_ZMiJB8')
TARGETS = [ORIGIN/'stages/03_place', LIGHT/'stages/04_cts']


def overlaps(first, second):
    return first == second or first in second.parents or second in first.parents


def process_paths():
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            data = (directory/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            yield data
            for name in ('cwd', 'exe'):
                yield str((directory/name).resolve())
            for fd in (directory/'fd').iterdir():
                yield str(fd.resolve())
        except (OSError, RuntimeError):
            continue


def main():
    if sys.platform != 'linux':
        raise SystemExit('Run this script on the Linux server')
    apply = sys.argv[1:] == ['--apply']
    if sys.argv[1:] not in ([], ['--apply']):
        raise SystemExit('Usage: python3 CleanFailedPrCopies.py [--apply]')
    if not ACTIVE.is_dir():
        raise SystemExit('Expected active run directory absent')
    ledgers = [ORIGIN/'FinalOriginalLedger.json', LIGHT/'FinalOriginalLedger.json',
               ACTIVE/'ResumeInputs.json', ACTIVE/'CtsResumeSource.json']
    protected = []
    for file in ledgers:
        data = json.loads(file.read_text())
        if file.name == 'FinalOriginalLedger.json':
            items = list(data['files']) + list(data['libraries'])
        else:
            items = [data['checkpoint']]
        protected.extend(Path(item) for item in items if item.startswith('/'))
    paths = list(process_paths())
    plans = []
    for stage in TARGETS:
        target = stage/'system_707cd7f.nlib'
        if not target.exists():
            print('ALREADY_ABSENT', target)
            continue
        status = json.loads((stage/'ActionResult.json').read_text())
        if status.get('native_exit') != 124 or status.get('core_saved') is not False:
            raise ValueError('Expected unsaved timeout copy: '+str(stage))
        if target.is_symlink() or target.resolve() != target or target.stat().st_uid != os.getuid():
            raise ValueError('Unexpected path or owner: '+str(target))
        if any(overlaps(target, item) for item in protected):
            raise ValueError('Dependency ledger protects '+str(target))
        if any(str(target) in item for item in paths):
            raise ValueError('Process still references '+str(target))
        size = sum(item.stat().st_size for item in target.rglob('*')
                   if item.is_file() and not item.is_symlink())
        plans.append((target, size))
        print('DELETE_LIBRARY_ONLY' if apply else 'CANDIDATE_LIBRARY_ONLY', size, target)
    report = {'apply': apply, 'targets': [{'path': str(p), 'logical_bytes': n} for p, n in plans]}
    report_path = ACTIVE/('CleanupApplied.json' if apply else 'CleanupPreview.json')
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    if apply:
        for target, size in plans:
            shutil.rmtree(str(target))
            print('REMOVED', target)
    print('LOGICAL_BYTES', sum(size for target, size in plans))
    print('REPORT', report_path)


if __name__ == '__main__':
    main()
