"""Generate the isolated sequential/combinational model diagnostic entry."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parts, hashes = [], []
for index, name in enumerate(('ReadProbe.py', 'PrepareCone.py', 'GateFeedbackSmoke.sv', 'GateIcbSmoke.sv')):
    data = (HERE / name).read_bytes().replace(b'\r\n', b'\n')
    if not data.endswith(b'\n'):
        data += b'\n'
    marker = f'TPUSOC_CONE_SOURCE_{index}'
    if marker in data.decode().splitlines():
        raise ValueError('Unsafe heredoc terminator')
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_CONE_HASHES\'\n' + ''.join(hashes) + 'TPUSOC_CONE_HASHES\n')
template = (HERE / 'RunCone.sh').read_text()
if template.count('# __CONE_TOOLS__') != 1:
    raise ValueError('Missing embedding marker')
data = template.replace('# __CONE_TOOLS__', '\n'.join(parts)).replace('\r\n', '\n').encode()
out = ROOT / 'workspace/Server/tpusoc_gate_cone_20261105_v1.sh'
if out.exists() and out.read_bytes() != data:
    raise ValueError('Refusing to replace a versioned artifact')
out.write_bytes(data)
print('ARTIFACT', out)
print('BYTES', len(data))
print('SHA256', hashlib.sha256(data).hexdigest())
