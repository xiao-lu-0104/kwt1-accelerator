"""Small standalone native runner: no old design/package discovery."""
import hashlib
import json
from pathlib import Path
import subprocess
import time


def load(p):return json.loads(Path(p).read_text())
def save(p,d):Path(p).write_text(json.dumps(d,indent=2)+'\n')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def tcl(p):
    p=str(p)
    if any(c in p for c in '{}\r\n'):raise ValueError('Unsupported Tcl path')
    return '{'+p.replace('\\','/')+'}'


def native(command,cwd,marker):
    log=cwd/'native.log'
    if log.exists():raise ValueError('Prior attempt retained: '+str(log))
    with log.open('wb') as f:
        proc=subprocess.Popen(command,cwd=str(cwd),stdout=f,stderr=subprocess.STDOUT)
        started=time.monotonic();beat=0
        print('NATIVE_PID={} LOG={}'.format(proc.pid,log),flush=True)
        while proc.poll() is None:
            time.sleep(5);elapsed=int(time.monotonic()-started)
            if elapsed//60>beat:
                beat=elapsed//60;print('HEARTBEAT elapsed={}s bytes={}'.format(elapsed,log.stat().st_size),flush=True)
    text=log.read_text(errors='replace')
    if proc.returncode or marker not in text or '\nError:' in text:
        print(text[-7000:],flush=True)
        raise ValueError('Native attempt incomplete; checkpoints/log retained: '+str(cwd))
