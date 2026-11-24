"""Wait for the retained native CTS, release its paused watcher, then resume PR."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

RUN = Path('/tmp/tpusoc_cts_resume_707cd7f_ZMiJB8')
WATCH_PID = 310880
STAGE = RUN/'stages/04_cts'


def proc(pid):
    try:
        directory = Path('/proc')/str(pid)
        fields = (directory/'stat').read_text().rsplit(')', 1)[1].split()
        return {'state': fields[0], 'parent': int(fields[1]),
                'group': int(fields[2]), 'exit_status': int(fields[49]) if len(fields)>49 else None,
                'command': (directory/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')}
    except FileNotFoundError:
        return None


def wait_native(watch_pid, parent_pid, tool_pid):
    while True:
        state = proc(tool_pid)
        if state is None or state['state'] == 'Z':
            if state and state['exit_status'] not in (None, 0):
                raise RuntimeError('Native wrapper exit status '+str(state['exit_status']))
            break
        watcher = proc(watch_pid)
        if not watcher or watcher['state'] not in ('T', 't'):
            raise RuntimeError('Watcher is no longer paused; inspect current processes')
        log = STAGE/'native.log'
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size-1500))
            lines = stream.read().decode(errors='replace').splitlines()
        print('WAIT_CTS_NATIVE: state='+state['state']+' log_bytes='+str(log.stat().st_size), flush=True)
        if lines:
            print('LAST_NATIVE_LINE: '+lines[-1][-240:], flush=True)
        time.sleep(30)
    text = (STAGE/'native.log').read_text(errors='replace')
    if 'CONTINUE_PHASE_COMPLETE: 04_cts' not in text or 'CONTINUE_CORE_SAVED: 04_cts' not in text:
        raise RuntimeError('Native CTS ended without successful completion and saved checkpoint')
    if not (STAGE/'checkpoint.def').is_file():
        raise RuntimeError('Saved CTS DEF absent')
    # CTS has exited and saved. The original watcher may now report its expired deadline.
    watcher = proc(watch_pid)
    if watcher and 'StageWatch.py' in watcher['command'] and str(RUN) in watcher['command']:
        os.kill(watch_pid, signal.SIGCONT)
    print('CTS_NATIVE_COMPLETE: checkpoint retained; waiting for original wrapper to finish', flush=True)
    while True:
        parent = proc(parent_pid)
        if parent is None or parent['state'] == 'Z':
            break
        time.sleep(2)


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Run on the Linux server')
    lock = (RUN/'CtsBridge.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (RUN/'CtsBridgeHandoff.json').exists():
        raise RuntimeError('Bridge already handed off; read CtsBridgeHandoff.json')
    watcher = proc(WATCH_PID)
    if not watcher or not all(token in watcher['command'] for token in ('StageWatch.py', str(RUN), 'stages/04_cts')):
        raise RuntimeError('Expected watcher identity not found')
    if watcher['state'] not in ('T', 't'):
        raise RuntimeError('Expected paused watcher')
    parent_pid = watcher['parent']
    parent = proc(parent_pid)
    if not parent or 'ContinuePr.py' not in parent['command'] or str(RUN) not in parent['command']:
        raise RuntimeError('Unexpected controlling parent')
    children = (Path('/proc')/str(WATCH_PID)/'task'/str(WATCH_PID)/'children').read_text().split()
    if len(children) != 1:
        raise RuntimeError('Expected one native tool wrapper')
    tool_pid = int(children[0])
    tool = proc(tool_pid)
    if not tool or tool['group'] == watcher['group']:
        raise RuntimeError('Native tool process group is not isolated')
    print('MONITORING_CTS: wrapper_pid='+str(tool_pid)+' watcher_pid='+str(WATCH_PID), flush=True)
    wait_native(WATCH_PID, parent_pid, tool_pid)
    out = Path(tempfile.mkdtemp(prefix='tpusoc_after_cts_707cd7f_', dir='/tmp'))
    shutil.copytree(str(RUN/'tools'), str(out/'tools'))
    path = out/'tools/ContinuePr.py'
    code = path.read_text()
    old = "    current = Path('/tmp/tpusoc_pr_light_707cd7f_PhN4TK/stages/03_place/system_707cd7f.nlib')"
    if code.count(old) != 1:
        raise RuntimeError('Unexpected runner source')
    checkpoint = STAGE/'system_707cd7f.nlib'
    code = code.replace(old, '    current = Path('+repr(str(checkpoint))+')')
    start = code.index('IMPLEMENT=')
    end = code.index(']\n', start)+2
    # Export the first routed candidate promptly. Full optimization remains in the other workflow.
    code = code[:start]+"IMPLEMENT=[('05_route',10800),('07_export',1800)]\n"+code[end:]
    code = code.replace('NEW_707CD7F_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING',
                        'NEW_707CD7F_ROUTED_LAYOUT_ROUTE_OPT_PENDING')
    compile(code, str(path), 'exec')
    path.write_text(code)
    manifest = {'source_commit': '707cd7f4a0a4d416d11bac71112980079e0a9d34',
                'source_library': str(checkpoint), 'output_run': str(out),
                'native_cts_complete': True, 'route_opt': 'deferred until first layout export',
                'wrapper_timeout_after_native_completion': True}
    (RUN/'CtsBridgeHandoff.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (out/'BridgeInputs.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('WORK_DIR: '+str(out), flush=True)
    print('FLOW: completed CTS -> signal routing -> export -> final PG checks', flush=True)
    process = subprocess.Popen(['python3', '-u', str(path), str(out)], cwd=str(out),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), universal_newlines=True)
    with (out/'runner.log').open('x') as log:
        for line in process.stdout:
            log.write(line); log.flush()
            print(line, end='', flush=True)
    raise SystemExit(process.wait())


if __name__ == '__main__':
    main()
