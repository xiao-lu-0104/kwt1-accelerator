"""Package a read-only audit of completed task power reports and SAIF."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts,hashes=[],[]
for index,name in enumerate(('ReadProbe.py','ReviewTaskPower.py')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    if not data.endswith(b'\n'): data+=b'\n'
    marker=f'TPUSOC_POWER_REVIEW_SOURCE_{index}'
    if marker in data.decode().splitlines(): raise ValueError('Unsafe heredoc marker')
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_POWER_REVIEW_HASHES\'\n'+''.join(hashes)+'TPUSOC_POWER_REVIEW_HASHES\n')
template=(HERE/'RunPowerReview.sh').read_text()
if template.count('# __POWER_REVIEW_TOOLS__')!=1: raise ValueError('Missing embedding marker')
data=template.replace('# __POWER_REVIEW_TOOLS__','\n'.join(parts)).replace('\r\n','\n').encode()
out=ROOT/'workspace/Server/tpusoc_power_review_20261105_v2.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
print('ARTIFACT',out,'BYTES',len(data),'SHA256',hashlib.sha256(data).hexdigest())
