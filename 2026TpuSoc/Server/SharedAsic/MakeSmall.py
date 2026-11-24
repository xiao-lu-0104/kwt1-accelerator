"""Generate bounded real-cell/bridge diagnostics and corrected mirror."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
files = [(HERE / name, name) for name in ('ReadProbe.py', 'PrepareSmall.py',
    'GateCellSmoke.sv', 'GateIcbSmoke.sv', 'GateWatch.sv', 'IcbMirror.sv')]
parts, hashes = [], []
for index, (path, name) in enumerate(files):
    data = path.read_bytes().replace(b'\r\n', b'\n')
    if not data.endswith(b'\n'):
        data += b'\n'
    marker = f'TPUSOC_SMALL_SOURCE_{index}'
    if marker in data.decode().splitlines():
        raise ValueError('Unsafe heredoc terminator')
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_SMALL_HASHES\'\n' + ''.join(hashes) + 'TPUSOC_SMALL_HASHES\n')
template = (HERE / 'RunSmall.sh').read_text()
if template.count('# __SMALL_TOOLS__') != 1:
    raise ValueError('Missing embedding marker')
data = template.replace('# __SMALL_TOOLS__', '\n'.join(parts)).replace('\r\n', '\n').encode()
out = ROOT / 'workspace/Server/tpusoc_gate_small_20261105_v2.sh'
if out.exists() and out.read_bytes() != data:
    raise ValueError('Refusing to replace a versioned artifact')
out.write_bytes(data)
print('ARTIFACT', out)
print('BYTES', len(data))
print('SHA256', hashlib.sha256(data).hexdigest())
