#!/usr/bin/env bash
set -euo pipefail
src=/tmp/tpusoc_pr_light_707cd7f_PhN4TK
origin=/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L
out=$(mktemp -d /tmp/tpusoc_quick_layout_707cd7f_XXXXXX)
cp -a "$src/tools" "$out/"
python3 - "$src" "$origin" "$out" <<'PY'
import json
from pathlib import Path
import sys

src, origin, out = map(Path, sys.argv[1:])
checkpoint = src/'stages/03_place/system_707cd7f.nlib'
status = json.loads((checkpoint.parent/'ActionResult.json').read_text())
assert status['complete'] and status['core_saved']
inputs = json.loads((origin/'ContinueInputs.json').read_text())
assert inputs['source_commit'] == '707cd7f4a0a4d416d11bac71112980079e0a9d34'
path = out/'tools/ContinuePr.py'
code = path.read_text()
old = "    current = src/'stages/01_rc/system_707cd7f.nlib'"
assert code.count(old) == 1
code = code.replace(old, '    current = Path('+repr(str(checkpoint))+')')
start = code.index('IMPLEMENT=')
end = code.index(']\n', start)+2
code = code[:start] + "IMPLEMENT=[('04_build_clock',3600),('04_route_clock',3600),('05_route',10800),('07_export',1800)]\n" + code[end:]
code = code.replace('NEW_707CD7F_ROUTED_CANDIDATE_GENERATED_REVIEW_PENDING',
                    'NEW_707CD7F_QUICK_ROUTED_LAYOUT_REVIEW_PENDING')
code = code.replace("'placement':'legalize existing placement'",
                    "'flow':'split CTS; final_opto and route_opt omitted for engineering layout'")
compile(code, str(path), 'exec')
path.write_text(code)
path = out/'tools/ContinuePr.tcl'
code = path.read_text()
start = code.index('        04_cts {')
end = code.index('        05_route {', start)
code = code[:start] + '''        04_build_clock {
            CpReport clock_opt_manual.txt [list man clock_opt]
            set F [open clock_opt_manual.txt r];set Manual [read $F];close $F
            foreach Token {build_clock route_clock -from -to} {
                if {[string first $Token $Manual]<0} {error "Installed clock_opt manual lacks $Token"}
            }
            PrStep build_clock [list clock_opt -from build_clock -to build_clock]
            CpConnect;CpSave;CpTiming
        }
        04_route_clock {
            PrStep route_clock [list clock_opt -from route_clock -to route_clock]
            PrStep propagated_clock [list set_propagated_clock [all_clocks]]
            CpConnect;CpSave;CpTiming
        }
''' + code[end:]
path.write_text(code)
(out/'QuickLayoutInputs.json').write_text(json.dumps({
    'source_commit': inputs['source_commit'], 'checkpoint': str(checkpoint),
    'purpose': 'engineering routed layout with separate clock-build and clock-route checkpoints',
    'omitted_optimization': ['clock_opt final_opto', 'route_opt'],
    'limitations': 'Timing and PG violations require review. GDS export is optional and unmerged.'
}, indent=2)+'\n')
PY
cd "$out"
printf 'WORK_DIR: %s\nFLOW: split CTS checkpoints, signal route, export\n' "$out"
env PYTHONDONTWRITEBYTECODE=1 python3 -u tools/ContinuePr.py "$out" 2>&1 | tee runner.log
