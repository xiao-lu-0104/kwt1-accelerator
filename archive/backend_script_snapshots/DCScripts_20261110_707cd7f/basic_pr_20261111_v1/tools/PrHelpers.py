"""Inspected helper functions only; no historical design runner included."""
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from decimal import Decimal
from Preflight import lef_info,structural_references

HERE=Path(__file__).resolve().parent


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def verify(mapping):
    for name,digest in mapping.items():
        if sha(name)!=digest:raise ValueError('Input changed: '+name)


def scalar(name,value):
    value=str(value)
    if any(c in value for c in '{}\\\n\r'):raise ValueError('Unsafe Tcl scalar')
    return 'set '+name+' {'+value+'}\n'


def tlist(name,values):
    for value in values:scalar('x',value)
    return 'set '+name+' [list '+' '.join('{'+str(v)+'}' for v in values)+']\n'


def serialized_clock(text):
    units=re.findall(r'^\s*set_units\s+.*?-time\s+(\S+)',text,re.M)
    if units!=['ns']:raise ValueError('Expected one explicit ns SDC time unit')
    lines=[line for line in text.splitlines() if re.match(r'^\s*create_clock\s',line) and re.search(r'-name\s+\{?CoreClock\}?(?:\s|$)',line)]
    if len(lines)!=1:raise ValueError('Expected exactly one serialized CoreClock definition')
    periods=re.findall(r'-period\s+([0-9]+(?:\.[0-9]+)?)\b',lines[0])
    if len(periods)!=1:raise ValueError('Missing serialized numeric CoreClock period')
    value=Decimal(periods[0]);target=Decimal('6.666667')
    # DC writes six significant digits here. Accept only its exact decimal
    # rounding at >= five fractional digits, never an arbitrary looser budget.
    if value.as_tuple().exponent>-5 or value!=target.quantize(Decimal(1).scaleb(value.as_tuple().exponent)):
        raise ValueError('Serialized CoreClock is not a precise rounding of 6.666667 ns')
    return periods[0]


def tree(path):
    result={};total=0
    for p in sorted(path.rglob('*')):
        if p.is_symlink():raise ValueError('Symlink in reference library: '+str(p))
        if p.is_file():
            total+=p.stat().st_size
            if len(result)>50000 or total>2*1024**3:raise ValueError('Reference library snapshot exceeds bound')
            result[p.relative_to(path).as_posix()]=sha(p)
    if not result:raise ValueError('Empty physical reference library')
    return result


def native(out,label,cwd,exe,flag,script,limit):
    log=cwd/(label+'.log')
    code=subprocess.call(['python3',str(HERE/'StageWatch.py'),'--label',label,'--limit',str(limit),
        '--log',str(log),'--cwd',str(cwd),'--',str(exe),flag,str(script)])
    text=log.read_text(errors='replace')
    if code or re.search(r'^\s*(Error:|Fatal:)',text,re.M):
        print(text[-10000:],flush=True);raise ValueError('Native stage failed: '+label)
    return text


def geometry(stage,out,lef):
    units=(stage/'report_units.rpt').read_text()
    if not re.search(r'^\s*length\s*:\s*1\.0+um\s*$',units,re.M):raise ValueError('Native length unit is not confirmed as micrometers')
    rows=[]
    for line in (stage/'macros.tsv').read_text().splitlines()[1:]:
        name,ref,*coords=line.split('\t');b=list(map(float,coords))
        if len(b)!=4 or not all(math.isfinite(v) for v in b) or b[2]<=b[0] or b[3]<=b[1]:raise ValueError('Invalid native macro bbox')
        width,height=b[2]-b[0],b[3]-b[1]
        expected=lef[ref]
        rows.append({'name':name,'ref':ref,'bbox_um':b,'lef_size_um':expected,
            'native_size_um':[width,height],'native_bbox_area_minus_lef_um2':width*height-expected[0]*expected[1]})
    if len(rows)!=120 or sum(r['ref']=='RAMSP1024X16' for r in rows)!=56:raise ValueError('Wrong placed macro inventory')
    core=list(map(float,(stage/'core_bbox.txt').read_text().replace('{',' ').replace('}',' ').split()))
    if len(core)!=4:raise ValueError('Unexpected core bbox')
    for i,r in enumerate(rows):
        a,b,c,d=r['bbox_um']
        if a<core[0]-.001 or b<core[1]-.001 or c>core[2]+.001 or d>core[3]+.001:raise ValueError('Macro outside core: '+r['name'])
        for q in rows[:i]:
            e,f,g,h=q['bbox_um']
            if min(c,g)-max(a,e)>.001 and min(d,h)-max(b,f)>.001:raise ValueError('Native macro bboxes overlap')
    report=(stage/'report_placement.rpt').read_text()
    if not re.search(r'Total hard macro to hard macro overlaps:\s*0\b',report):raise ValueError('Native zero-overlap evidence missing')
    save(out/'MacroGeometry.json',{'core_bbox_um':core,'macros':rows,
        'scope':'native physical bbox containment/overlap; LEF dimension differences retained, not waived as DRC signoff'})
    w,h=core[2]-core[0],core[3]-core[1]
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s">'%(w,h),'<rect width="100%" height="100%" fill="#f3f5f7"/>']
    for r in rows:
        a,b,c,d=r['bbox_um'];color='#70b5dc' if r['ref']=='RAMSP1024X16' else '#e4b569'
        svg.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="#344456" stroke-width="0.5"><title>%s</title></rect>'%(a-core[0],core[3]-d,c-a,d-b,color,html.escape(r['name'])))
    (out/'MacroPlacement.svg').write_text('\n'.join(svg+['</svg>']))


