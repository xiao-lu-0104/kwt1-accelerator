#!/usr/bin/env bash
set -euo pipefail
src=/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L
cd "$src"
sha256sum --quiet -c PACKAGE.sha256
out=$(mktemp -d /tmp/tpusoc_pr_light_707cd7f_XXXXXX)
cp -a tools "$out/"
python3 - "$src" "$out" <<'PY'
import json
from pathlib import Path
import sys
src, out = map(Path, sys.argv[1:])
tools = out / 'tools'
checkpoint = src / 'stages/01_rc/system_707cd7f.nlib'
read = lambda p: json.loads(p.read_text())
assert read(src/'ContinueInputs.json')['source_commit'].startswith('707cd7f')
assert read(checkpoint.parent/'ActionResult.json')['complete']
assert read(src/'stages/03_place/ActionResult.json')['native_exit'] == 124
assert checkpoint.is_dir()
p = tools/'ContinuePr.tcl'
s = p.read_text()
line = '            PrStep optimize_placement [list place_opt]\n'
assert s.count(line) == 1
p.write_text(s.replace(line, '            puts "PLACEMENT_MODE: legalize_existing"\n'))
p = tools/'ContinuePr.py'
s = p.read_text()
a = s.index('    cfg=', s.index('def main('))
b = s.index('    def progress():', a)
s = s[:a] + """    src = Path('/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L')
    current = src/'stages/01_rc/system_707cd7f.nlib'
    before = tree(current)
    ledger = json.loads((src/'FinalOriginalLedger.json').read_text())
    originals = ledger['files']
    snapshots = dict(ledger['libraries'])
    snapshots[str(current)] = before
    for ref in src.glob('library_*/*.ndm'):
        snapshots[str(ref)] = tree(ref)
    common = ''.join(line+'\\n' for line in (current.parent/'ContinueConfig.tcl').read_text().splitlines()
                     if not line.startswith(('set DesignLib ', 'set Action ')))
    phy = Path.home()/'soc/tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json'
    physical = json.loads(phy.read_text())
    icc,flag = physical['icc2'],physical['icc2_flag']
    stages=[];trials=[];last_phase=None
    base=json.loads((src/'PgChecks_baseline_v6.json').read_text())
    selected=json.loads((src/'PgDecision.json').read_text())['checks']
    save(out/'ResumeInputs.json',{'source_commit':REV,'checkpoint':str(current),'fingerprint':before,
                                  'placement':'legalize existing placement'})
""" + s[b:]
a = s.index("    print('SOURCE_COMMIT:")
b = s.index('        for phase,limit in IMPLEMENT:', a)
s = s[:a] + "    try:\n        progress()\n" + s[b:]
s = s.replace("IMPLEMENT=[('01_rc',1800),('03_place',7200)", "IMPLEMENT=[('03_place',1800)")
compile(s, str(p), 'exec')
p.write_text(s)
PY
cd "$out"
nohup env PYTHONDONTWRITEBYTECODE=1 python3 -u tools/ContinuePr.py "$out" >runner.log 2>&1 </dev/null &
printf 'WORK_DIR: %s\nPID: %s\n' "$out" "$!"
