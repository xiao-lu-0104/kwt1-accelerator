"""Remove explicitly retired tpusoc runs after final delivery verification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def main(apply):
    soc = (Path.home()/'soc').resolve()
    saved = soc/'pr_saved'
    for name in ('PR_707cd7f_20261111', 'DC_POWER_707cd7f_20261111', 'PROCESS_1110_707cd7f'):
        package = saved/(name+'.tar.gz')
        expected = Path(str(package)+'.sha256').read_text().split()[0].lower()
        if digest(package) != expected:
            raise RuntimeError('Backup SHA mismatch: '+str(package))
    if not (saved/'OpenFinalPr.tcl').is_file() or not (saved/'PR_VIEW').is_dir():
        raise RuntimeError('Persistent layout missing')
    targets = []
    for parent in (soc, Path('/tmp')):
        for p in parent.iterdir():
            if not p.name.startswith('tpusoc') or p.is_symlink():
                continue
            if p.stat().st_uid != os.getuid() or not p.is_dir():
                continue
            resolved = p.resolve()
            if resolved.parent != parent or resolved == saved:
                raise RuntimeError('Unsafe target: '+str(p))
            targets.append(resolved)
    # Never delete a run used by a live process, including a GUI or shell cwd.
    blocked = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            cwd = os.readlink(str(process/'cwd'))
            args = (process/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            for p in targets:
                if cwd == str(p) or cwd.startswith(str(p)+'/') or str(p)+'/' in args:
                    blocked.append({'pid': process.name, 'run': str(p), 'cwd': cwd})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    if blocked:
        print(json.dumps(blocked, indent=2))
        raise RuntimeError('Runs still in use. Close GUIs and cd home in their terminals.')
    record = saved/('Cleanup_'+time.strftime('%Y%m%d_%H%M%S')+'.json')
    state = {'mode': 'apply' if apply else 'preview', 'targets': [str(p) for p in targets], 'removed': []}
    record.write_text(json.dumps(state, indent=2)+'\n')
    for p in targets:
        print(('DELETE: ' if apply else 'CANDIDATE: ')+str(p), flush=True)
        if apply:
            shutil.rmtree(str(p))
            state['removed'].append(str(p))
            record.write_text(json.dumps(state, indent=2)+'\n')
    print('CLEANUP_COMPLETE' if apply else 'PREVIEW_COMPLETE', 'directories='+str(len(targets)))
    print('RETAINED:', saved)
    print('MANIFEST:', record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
