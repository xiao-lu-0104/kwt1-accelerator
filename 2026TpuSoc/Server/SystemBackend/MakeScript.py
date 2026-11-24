"""Build a self-contained current-system mapping and evidence archive entry."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sources={name:HERE/name for name in ('Prepare.py','Summarize.py','StageWatch.py','TcmMacro.sv','TcmContract.sv','CompileLib.tcl','System.tcl')}
sources['AsicCommon.tcl']=HERE.parent/'Backend/AsicCommon.tcl'
parts=[]; hashes=[]
for index,(name,path) in enumerate(sources.items()):
    data=path.read_bytes().replace(b'\r\n',b'\n')
    if not data.endswith(b'\n'): data+=b'\n'
    marker=f'TPUSOC_SYSTEM_BASE_SOURCE_{index}'
    if marker in data.decode().splitlines(): raise ValueError('Unsafe marker')
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_SYSTEM_BASE_HASHES\'\n'+''.join(hashes)+'TPUSOC_SYSTEM_BASE_HASHES\n')
template=(HERE/'Run.sh').read_text()
if template.count('# __SYSTEM_BASE_TOOLS__')!=1: raise ValueError('Missing embedding marker')
data=template.replace('# __SYSTEM_BASE_TOOLS__','\n'.join(parts)).replace('\r\n','\n').encode()
out=ROOT/'workspace/Server/tpusoc_system_base_20261106_v2.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
print('ARTIFACT',out,'BYTES',len(data),'SHA256',hashlib.sha256(data).hexdigest())
