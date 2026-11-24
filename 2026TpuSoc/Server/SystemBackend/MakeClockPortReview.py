"""Build an immutable report-only clock-output constraint correction entry."""
import base64
import gzip
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=['''#!/usr/bin/env bash
set -euo pipefail
source_run="$HOME/soc/tpusoc_system_base_20261106_GamjxW"
[[ -s "$source_run/SystemBaseRecoveryInputs.json" ]] || { echo "ERROR: Missing recovered run $source_run"; exit 2; }
dc_bin=${DC_BIN:-$(command -v dc_shell || true)}
[[ -n "$dc_bin" ]] || dc_bin=/eda/synopsys/dc/dc_2022.03-SP5/bin/dc_shell
[[ -x "$dc_bin" ]] || { echo 'ERROR: dc_shell not found'; exit 2; }
work=$(mktemp -d "$HOME/soc/tpusoc_clock_port_review_20261106_XXXXXX")
tools="$work/tools"; mkdir -p "$tools"
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; if ((rc)); then echo "RESULT: CLOCK_PORT_REVIEW_FAILED exit=$rc"; echo "WORK_DIR: $work"; fi' EXIT
echo "WORK_DIR: $work"
echo 'MODE: existing DDC report only; two forwarded clock outputs corrected; other data constraints and netlist preserved'
echo 'LIMIT: input verification 3min; report-only DC 8min; no synthesis or simulation'
''']
names={n:HERE/n for n in ('Prepare.py','ClockPortReview.py','ClockPortReview.tcl','AreaBreakdown.tcl','StageWatch.py')}
names['AsicCommon.tcl']=HERE.parent/'Backend/AsicCommon.tcl'
hashes=[]
for index,(name,path) in enumerate(names.items()):
    data=path.read_bytes().replace(b'\r\n',b'\n')
    marker=f'TPUSOC_CLOCK_REVIEW_SOURCE_{index}'
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_CLOCK_REVIEW_HASHES\'\n'+''.join(hashes)+'TPUSOC_CLOCK_REVIEW_HASHES\n')
parts.append('''(cd "$tools"; sha256sum --quiet -c MANIFEST.sha256)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tools"
python3 -B -u "$tools/StageWatch.py" --label verify_inputs --limit 180 --log "$work/prepare.log" --cwd "$work" -- python3 -B -u "$tools/ClockPortReview.py" prepare "$work" --source "$source_run"
tail -n 2 "$work/prepare.log"
export TPU_CLOCK_OUT="$work" TPU_CLOCK_TOOLS="$tools" TPU_CLOCK_DDC="$source_run/mapped/candidate.ddc"
export TPU_STDCELL_DB TPU_SRAM_DB TPU_SYSTEM_DB
TPU_STDCELL_DB=$(cat "$source_run/StdDb.txt")
TPU_SRAM_DB=$(cat "$source_run/SpDb.txt")
TPU_SYSTEM_DB="$source_run/sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db"
if ! python3 -B -u "$tools/StageWatch.py" --label report_clock_ports --limit 480 --log "$work/dc.log" --cwd "$work" -- "$dc_bin" -f "$tools/ClockPortReview.tcl"; then
    tail -n 22 "$work/dc.log"; exit 1
fi
if grep -Eq '^(Error:|CLOCK_PORT_REPORT_ERROR:)' "$work/dc.log"; then tail -n 24 "$work/dc.log"; exit 1; fi
python3 -B -u "$tools/ClockPortReview.py" finish "$work"
echo "WORK_DIR: $work"
''')
data=''.join(parts).encode()
out=ROOT/'workspace/Server/tpusoc_clock_port_review_20261106_v3.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
digest=hashlib.sha256(data).hexdigest(); payload=base64.b64encode(gzip.compress(data,mtime=0)).decode()
code='import base64,gzip,hashlib,os; from pathlib import Path; d=gzip.decompress(base64.b64decode("'+payload+'")); assert hashlib.sha256(d).hexdigest()=="'+digest+'"; p=Path.home()/"Desktop"/"'+out.name+'"; assert not p.exists() or p.read_bytes()==d,"Existing version differs; stopped"; p.write_bytes(d); print("LOCAL_TRANSFER_OK SHA256='+digest+'",flush=True); os.execvp("bash",["bash",str(p)])'
out.with_suffix('.paste.txt').write_text("python3 -c '"+code+"'\n")
print('ARTIFACT',out,'BYTES',len(data),'SHA256',digest)
