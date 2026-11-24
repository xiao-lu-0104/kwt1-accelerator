#!/usr/bin/env bash
set -euo pipefail
src=/tmp/tpusoc_pr_light_707cd7f_PhN4TK
origin=/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L
out=$(mktemp -d /tmp/tpusoc_cts_resume_707cd7f_XXXXXX)
cp -a "$src/tools" "$out/"
python3 - "$src" "$origin" "$out" <<'PY'
import json
from pathlib import Path
import sys

src, origin, out = map(Path, sys.argv[1:])
read = lambda path: json.loads(path.read_text())
checkpoint = src / 'stages/03_place/system_707cd7f.nlib'
assert read(origin/'ContinueInputs.json')['source_commit'] == '707cd7f4a0a4d416d11bac71112980079e0a9d34'
status = read(checkpoint.parent/'ActionResult.json')
assert status['complete'] and status['core_saved']
assert read(src/'stages/04_cts/ActionResult.json')['native_exit'] == 124
assert read(src/'ContinueFailure.json')['last_successful_library'] == str(checkpoint)
assert checkpoint.is_dir() and (checkpoint.parent/'checkpoint.def').stat().st_size

path = out/'tools/ContinuePr.py'
code = path.read_text()
old = "    current = src/'stages/01_rc/system_707cd7f.nlib'"
assert code.count(old) == 1
code = code.replace(old, '    current = Path('+repr(str(checkpoint))+')')
old = "IMPLEMENT=[('03_place',1800),('04_cts',7200)"
assert code.count(old) == 1
code = code.replace(old, "IMPLEMENT=[('04_cts',21600)")
code = code.replace("'placement':'legalize existing placement'", "'resume':'completed placement; CTS limit 21600 seconds'")
compile(code, str(path), 'exec')
path.write_text(code)
(out/'CtsResumeSource.json').write_text(json.dumps({
    'source_commit': read(origin/'ContinueInputs.json')['source_commit'],
    'source_run': str(src), 'checkpoint': str(checkpoint),
    'cts_limit_seconds': 21600, 'reason': 'previous CTS terminated at 7200 seconds'
}, indent=2)+'\n')
PY
cd "$out"
printf 'WORK_DIR: %s\nCTS_LIMIT_SECONDS: 21600\n' "$out"
env PYTHONDONTWRITEBYTECODE=1 python3 -u tools/ContinuePr.py "$out" 2>&1 | tee runner.log
