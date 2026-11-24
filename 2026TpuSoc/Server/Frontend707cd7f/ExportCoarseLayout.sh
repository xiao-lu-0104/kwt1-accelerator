#!/usr/bin/env bash
set -euo pipefail
out=$(mktemp -d /tmp/tpusoc_coarse_export_707cd7f_XXXXXX)
src=/tmp/tpusoc_pr_light_707cd7f_PhN4TK
cp -a "$src/tools" "$out/"
python3 - "$src" "$out" <<'PY'
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

src, out = map(Path, sys.argv[1:])
tools = out/'tools'
sys.path.insert(0, str(tools))
from PrHelpers import scalar, tree

source = src/'stages/03_place/system_707cd7f.nlib'
status = json.loads((source.parent/'ActionResult.json').read_text())
assert status['complete'] and status['core_saved']
origin = Path('/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L')
inputs = json.loads((origin/'ContinueInputs.json').read_text())
assert inputs['source_commit'] == '707cd7f4a0a4d416d11bac71112980079e0a9d34'
before = tree(source)
design = out/'design'
design.mkdir()
lib = design/'system_707cd7f.nlib'
shutil.copytree(str(source), str(lib))
assert tree(lib) == before
config = ''.join(line+'\n' for line in (source.parent/'ContinueConfig.tcl').read_text().splitlines()
                 if not line.startswith(('set DesignLib ', 'set Action ')))
(design/'ContinueConfig.tcl').write_text(config+scalar('DesignLib',lib)+scalar('Action','coarse_export'))
path = tools/'ContinuePr.tcl'
code = path.read_text()
anchor = '        04_cts {'
assert code.count(anchor) == 1
action = '''        coarse_export {
            CpSave
            PrStep coarse_verilog [list write_verilog coarse.v]
            PrNeed write_sdc {}
            set F [open write_sdc_manual.txt r];set Text [read $F];close $F
            if {[string first -output $Text]>=0} {
                PrStep coarse_sdc [list write_sdc -output coarse.sdc]
            } else {PrStep coarse_sdc [list write_sdc coarse.sdc]}
            CpReport legality.rpt [list check_legality]
            if {[llength [info commands write_gds]]} {
                CpReport gds_export.log [list write_gds coarse_unmerged.gds]
            }
        }
'''
path.write_text(code.replace(anchor, action+anchor))
physical = json.loads((Path.home()/'soc/tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json').read_text())
print('WORK_DIR: '+str(out), flush=True)
result = subprocess.call(['python3',str(tools/'StageWatch.py'),'--label','coarse_export',
    '--limit','1200','--log',str(design/'native.log'),'--cwd',str(design),'--',
    physical['icc2'],physical['icc2_flag'],str(path)])
text = (design/'native.log').read_text(errors='replace')
if result or 'CONTINUE_PHASE_COMPLETE: coarse_export' not in text:
    print(text[-6000:], flush=True)
    raise SystemExit('COARSE_EXPORT_FAILED: see native.log')
for name in ('checkpoint.def','coarse.v','coarse.sdc'):
    assert (design/name).stat().st_size
assert tree(source) == before
(out/'OpenCoarseLayout.tcl').write_text('open_lib {'+str(lib)+'}\nopen_block e203_cpu_top\nstart_gui\n')
gds = design/'coarse_unmerged.gds'
summary = {'source_commit':inputs['source_commit'],'source_library':str(source),
    'library':str(lib),'def':str(design/'checkpoint.def'),
    'scope':'saved legal placement and existing PG; CTS and signal routing incomplete',
    'source_unchanged':True,'unmerged_gds_exists':gds.is_file() and gds.stat().st_size>0,
    'pg_status':'known unresolved connectivity and DRC violations',
    'result':'NEW_707CD7F_COARSE_PLACEMENT_EXPORTED'}
(out/'CoarseLayoutSummary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('RESULT: '+summary['result'],flush=True)
print('OPEN_GUI: '+physical['icc2']+' -file '+str(out/'OpenCoarseLayout.tcl'),flush=True)
PY
