"""Checkpointed 1109 system implementation through PG, place, CTS and routing."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

HERE=Path(__file__).resolve().parent
PHASES=[('01_rc',900),('02_pg',2400),('03_place',3600),('04_cts',3600),
        ('05_route',7200),('06_route_opt',3600),('07_export',1800)]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def verify(record):
    for name,digest in record.items():
        if sha(name)!=digest:raise ValueError('Input changed: '+name)


def tree(root):
    result={};total=0
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('Library symlink requires review: '+str(p))
        if p.is_file():
            total+=p.stat().st_size
            if total>4*1024**3 or len(result)>60000:raise ValueError('Library snapshot exceeds limit')
            result[p.relative_to(root).as_posix()]=sha(p)
    if not result:raise ValueError('Empty library: '+str(root))
    return result


def scalar(name,value):
    value=str(value)
    if any(c in value for c in '{}\\\r\n'):raise ValueError('Unsafe Tcl value')
    return 'set '+name+' {'+value+'}\n'


def tlist(name,values):
    for value in values:scalar('x',value)
    return 'set '+name+' [list '+' '.join('{'+str(v)+'}' for v in values)+']\n'


def layer_map(text):
    sections={};current=None
    for line in text.splitlines():
        fields=line.split('#',1)[0].strip().split()
        if not fields or fields[0].startswith(';'):continue
        if fields[0] in ('conducting_layers','via_layers','marker_layers','remove_layers'):
            current=fields[0];sections[current]={};continue
        if current and len(fields)>=2:sections[current][fields[0]]=fields[1]
    return sections


def select_rc(inventory):
    if inventory['map_inventory']['truncated']:raise ValueError('Mapping inventory incomplete')
    rc=[r for r in inventory['rc_candidates'] if Path(r['path']).name=='StarRC_40LL_1P8M_1TM_TYP.tluplus']
    maps=[m for m in inventory['map_inventory']['candidates'] if Path(m['path']).name=='StarRC_40LL_1P8M_1TM_cell.map']
    pairs=[(r,m) for r in rc for m in maps if Path(r['path']).parent==Path(m['path']).parent]
    if len(pairs)!=1:raise ValueError('Expected unique same-directory RVT 1P8M_1TM TYP/map pair')
    r,m=pairs[0];verify({r['path']:r['sha256'],m['path']:m['sha256']})
    mapping=layer_map(Path(m['path']).read_text())
    conduct={'GT':'npoly','ALPA':'alpa','TM2':'metal8'}
    conduct.update({'M'+str(i):'metal'+str(i) for i in range(1,8)})
    vias={'CT':'npolyCont','TV2':'via7','PA':'viapa'}
    vias.update({'V'+str(i):'via'+str(i) for i in range(1,7)})
    if mapping.get('conducting_layers')!=conduct or mapping.get('via_layers')!=vias:
        raise ValueError('RC mapping is not the native M1..M7+TM2 one-thick-metal stack')
    return {'tlup':r['path'],'map':m['path'],'mapping':mapping,
        'model':'TYP707CONT','corner':'INITIAL','early_late':'same TYP, 25C engineering trial; not MCMM worst-corner signoff'}


def operational_errors(text):
    checking=False;errors=[]
    for line in text.splitlines():
        if line.startswith('FULL_PR_CHECK_BEGIN:'):checking=True
        elif line.startswith('FULL_PR_CHECK_END:'):checking=False
        elif re.match(r'^\s*Fatal:',line) or (re.match(r'^\s*Error:',line) and not checking):errors.append(line)
    return errors


def routed_nets(path):
    inside=False;count=0
    with path.open(errors='replace') as f:
        for line in f:
            if re.match(r'^\s*NETS\s+\d+',line):inside=True
            elif re.match(r'^\s*END\s+NETS',line):inside=False
            elif inside and re.search(r'\+\s+(?:ROUTED|FIXED|COVER)\b',line):count+=1
    return count

