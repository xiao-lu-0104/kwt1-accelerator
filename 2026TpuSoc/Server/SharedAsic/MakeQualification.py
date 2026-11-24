"""Package passive task qualification, actual macro smoke and Power Compiler clock query."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts=[]; hashes=[]
for index,name in enumerate(('ReadProbe.py','PrepareQualification.py',
    'SummarizeQualification.py','QualificationWindow.sv','QualificationClock.tcl','SharedMacroSmoke.sv')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    if not data.endswith(b'\n'): data+=b'\n'
    marker=f'TPUSOC_QUAL_SOURCE_{index}'
    if marker in data.decode().splitlines(): raise ValueError('Unsafe marker')
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_QUAL_HASHES\'\n'+''.join(hashes)+'TPUSOC_QUAL_HASHES\n')
template=(HERE/'RunQualification.sh').read_text()
if template.count('# __QUALIFICATION_TOOLS__')!=1: raise ValueError('Missing marker')
data=template.replace('# __QUALIFICATION_TOOLS__','\n'.join(parts)).replace('\r\n','\n').encode()
out=ROOT/'workspace/Server/tpusoc_activity_qualification_20261106_v2.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
print('ARTIFACT',out,'BYTES',len(data),'SHA256',hashlib.sha256(data).hexdigest())
