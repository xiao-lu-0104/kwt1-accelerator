"""Make a standalone, read-only v5 candidate reporting script."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sources = [(ROOT/'Server/Backend/AsicCommon.tcl', 'AsicCommon.tcl')]
sources += [(HERE/name, name) for name in
            ('HoldPolicy.tcl', 'SnapshotHold.tcl', 'VerifyHoldInputs.py', 'HoldReport.py', 'Reports.tcl')]
parts, manifest = [], []
for index, (path, name) in enumerate(sources):
    data = path.read_bytes().replace(b'\r\n', b'\n')
    if not data.endswith(b'\n'):
        data += b'\n'
    text = data.decode('utf-8')
    marker = 'TPUSOC_HOLD_REPORT_SOURCE_%d' % index
    if marker in text.splitlines():
        raise ValueError('Unsafe heredoc terminator')
    parts.append('cat > "$tools/%s" <<\'%s\'\n%s%s\n' % (name, marker, text, marker))
    manifest.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_HOLD_REPORT_HASHES\'\n'+''.join(manifest)+'TPUSOC_HOLD_REPORT_HASHES\n')
script = (HERE/'RunHoldReport.sh').read_text().replace('\r\n', '\n')
marker = '# __HOLD_REPORT_TOOLS__'
if script.count(marker) != 1:
    raise ValueError('Missing unique insertion marker')
data = script.replace(marker, '\n'.join(parts)).encode('utf-8')
target = ROOT/'workspace/Server/tpusoc_sram_hold_report_20261102_v5b.sh'
if target.exists() and target.read_bytes() != data:
    raise ValueError('Refusing to change an existing artifact')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(data)
print('ARTIFACT', target)
print('BYTES', len(data))
print('SHA256', hashlib.sha256(data).hexdigest())
