"""Make one portable report-only shell script, embedding its exact Tcl sources."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parts = []
for index, name in enumerate(('AsicCommon.tcl', 'AsicCdc.tcl', 'AsicReports.tcl', 'ReportCheckpoint.tcl')):
    text = (HERE / name).read_text().replace('\r\n', '\n')
    marker = 'TPUSOC_REPORT_TCL_%d' % index
    if marker in text.splitlines():
        raise ValueError('Unexpected heredoc terminator in '+name)
    parts.append('cat > "$work/tools/%s" <<\'%s\'\n%s\n%s\n' % (name, marker, text.rstrip('\n'), marker))
script = (HERE / 'ReportOnly.sh').read_text().replace('\r\n', '\n')
needle = '# __REPORT_TOOLS__'
if script.count(needle) != 1:
    raise ValueError('Missing unique source insertion marker')
script = script.replace(needle, '\n'.join(parts))
target = ROOT / 'workspace/Server/tpusoc_asic_report_fix_20261102_v3d.sh'
data = script.encode()
if target.exists() and target.read_bytes() != data:
    raise ValueError('Refusing to change an existing recovery artifact')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(data)
print('ARTIFACT', target)
print('BYTES', len(data))
print('SHA256', hashlib.sha256(data).hexdigest())
