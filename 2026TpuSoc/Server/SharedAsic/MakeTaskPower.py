"""Package full-task passive SAIF capture and read-only annotated estimates."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parts,hashes=[],[]
for index,name in enumerate(('ReadProbe.py','PreparePower.py','SummarizePower.py','PrepareTaskPower.py',
                            'TaskActivity.sv','TaskPower.tcl','SummarizeTaskPower.py','IcbMirror.sv','GateWatch.sv')):
    data=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    if not data.endswith(b'\n'): data+=b'\n'
    marker=f'TPUSOC_TASK_POWER_SOURCE_{index}'
    if marker in data.decode().splitlines(): raise ValueError('Unsafe heredoc marker')
    parts.append(f'cat > "$tools/{name}" <<\'{marker}\'\n{data.decode()}{marker}\n')
    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
parts.append('cat > "$tools/MANIFEST.sha256" <<\'TPUSOC_TASK_POWER_HASHES\'\n'+''.join(hashes)+'TPUSOC_TASK_POWER_HASHES\n')
template=(HERE/'RunTaskPower.sh').read_text()
if template.count('# __TASK_POWER_TOOLS__')!=1: raise ValueError('Missing embedding marker')
data=template.replace('# __TASK_POWER_TOOLS__','\n'.join(parts)).replace('\r\n','\n').encode()
out=ROOT/'workspace/Server/tpusoc_task_power_20261105_v1.sh'
if out.exists() and out.read_bytes()!=data: raise ValueError('Refusing to replace versioned artifact')
out.write_bytes(data)
print('ARTIFACT',out,'BYTES',len(data),'SHA256',hashlib.sha256(data).hexdigest())
