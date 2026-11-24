"""Build an isolated restart launcher for the native CTS IO audit failure."""
import base64
import gzip
import hashlib
from pathlib import Path
from BuildFastEngineeringPr import build_tcl

here = Path(__file__).resolve().parent
root = here.parents[1]
old = (here/'FastEngineeringPr.tcl').read_bytes().replace(b'\r\n', b'\n')
new = build_tcl().encode().replace(b'\r\n', b'\n')
assert old != new
old_sha = hashlib.sha256(old).hexdigest()
new_sha = hashlib.sha256(new).hexdigest()
payload = base64.b64encode(gzip.compress(new)).decode()
shell = '''#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import base64,gzip,hashlib,json
from pathlib import Path
root = Path.cwd().resolve()
if not root.name.startswith('tpusoc_basic_pr_707cd7f_') or root.parent != Path('/tmp'):
    raise SystemExit('Run from the existing /tmp/tpusoc_basic_pr_707cd7f_* directory')
f = root/'FastPrProgress.json'
p = json.loads(f.read_text())
if not (any(s['stage']=='02_pg_basic' and s['complete'] for s in p['stages']) and any(s['stage']=='04_build_clock' and not s['complete'] for s in p['stages']) and not (root/'FastPrSummary.json').exists()):
    raise SystemExit('Expected completed PG and failed CTS; original untouched')
target = root/'tools/FastEngineeringPr.tcl'
old = target.read_bytes()
if hashlib.sha256(old).hexdigest() != 'OLD_SHA':
    raise SystemExit('Frozen Tcl mismatch; original untouched')
backup = root/'tools/FastEngineeringPr.v1.tcl'
with backup.open('xb') as f: f.write(old)
new = gzip.decompress(base64.b64decode('PAYLOAD'))
if hashlib.sha256(new).hexdigest() != 'NEW_SHA':
    raise SystemExit('Repair payload mismatch; original untouched')
target.write_bytes(new)
print('REPAIRED_WORK_DIR:',root,flush=True)
print('OLD_TCL_BACKUP:',backup,flush=True)
print('NEW_TCL_SHA256:',hashlib.sha256(new).hexdigest(),flush=True)
(root/'FastIoRepair.json').write_text(json.dumps({'reason':'CTS-created extra PG ports suspected; original 971 signal IO geometry retained and checked','old_sha256':'OLD_SHA','new_sha256':'NEW_SHA','old_backup':str(backup)},indent=2)+'\\n')
(root/'ResumeFastIoRepair.sh').write_text('#!/usr/bin/env bash\\nset -euo pipefail\\ncd '+str(root)+'\\npython3 -u tools/FastEngineeringPr.py '+str(root)+' 2>&1 | tee -a runner.log\\n')
print('RESUME_COMMAND: bash '+str(root/'ResumeFastIoRepair.sh'),flush=True)
PY
python3 -u tools/FastEngineeringPr.py "$PWD" 2>&1 | tee -a runner.log
'''.replace('OLD_SHA',old_sha).replace('NEW_SHA',new_sha).replace('PAYLOAD',payload)
path = root/'workspace/Server/tpusoc_basic_pr_io_repair_20261111_707cd7f_v3.sh'
path.write_bytes(shell.encode())
print(path, len(shell), hashlib.sha256(shell.encode()).hexdigest(), old_sha, new_sha)
