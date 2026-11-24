"""Run one bounded tool process group, saving logs and printing minute progress."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import time


def stop(process,first=signal.SIGTERM):
    try: os.killpg(process.pid,first)
    except ProcessLookupError: return
    try: process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True); parser.add_argument('--limit',type=float,required=True)
    parser.add_argument('--log',type=Path,required=True); parser.add_argument('--cwd',type=Path,required=True)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args(); command=args.command
    if command[:1]==['--']: command=command[1:]
    if not command or args.limit<=0: parser.error('Positive limit and executable arguments required')
    started=time.monotonic(); print('RUN:',args.label,'log='+str(args.log),flush=True)
    with args.log.open('x') as log:
        process=subprocess.Popen(command,cwd=args.cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while True:
                remaining=args.limit-(time.monotonic()-started)
                if remaining<=0:
                    stop(process); result=124; print('STAGE_TIMEOUT:',args.label,flush=True); break
                try:
                    result=process.wait(timeout=min(60,remaining)); break
                except subprocess.TimeoutExpired:
                    print('STAGE_RUNNING:',args.label,'elapsed_seconds='+str(round(time.monotonic()-started)),flush=True)
        except KeyboardInterrupt:
            stop(process,signal.SIGINT); result=130
    print('STAGE_FINISHED:',args.label,'exit='+str(result),'elapsed_seconds='+str(round(time.monotonic()-started)),flush=True)
    return result if result>=0 else 128-result


if __name__=='__main__': raise SystemExit(main())
