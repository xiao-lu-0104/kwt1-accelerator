"""Fresh 1109 full-system ICC2 import and initial placement, reusing only physical libraries."""
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


def main(out):
    soc=Path.home()/'soc'
    runs=[]
    for p in soc.glob('tpusoc_new_system_dc_20261109_*'):
        if (p/'SystemSummary.json').is_file():
            d=json.loads((p/'SystemSummary.json').read_text())
            if d.get('result')=='NEW_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING' and d.get('original_inputs_unchanged') is True:runs.append(p)
    if len(runs)!=1:raise ValueError('Expected exactly one successful 1109 system DC')
    system=runs[0];record=json.loads((system/'SystemInputs.json').read_text());verify(record['sha256'])
    # Only 1109 system output is eligible for the design. Old PR files supply technology/NDM only.
    if '20261109' not in system.name:raise ValueError('Current design date mismatch')
    old=soc/'tpusoc_icc2_start_20261108_mTq1LE'
    old_summary=json.loads((old/'PrSummary.json').read_text())
    if old_summary.get('status')!='ICC2_IMPORT_AND_INITIAL_FLOORPLAN_COMPLETE_REVIEW_PENDING' or old_summary.get('inputs_unchanged') is not True:
        raise ValueError('Historical reference-library preparation was not successful')
    physical=json.loads((old/'PrInputs.json').read_text());verify(physical['inputs'])
    selection=physical['selection']
    original={str(old/'PrSummary.json'):sha(old/'PrSummary.json'),str(old/'PrInputs.json'):sha(old/'PrInputs.json')}
    original.update(record['sha256']);original.update(physical['inputs'])
    inputs=out/'inputs';inputs.mkdir()
    for name in ('candidate.v','candidate.sdc'):
        source=system/'mapped'/name;original[str(source)]=sha(source);shutil.copy2(str(source),str(inputs/name))
        if sha(inputs/name)!=original[str(source)]:raise ValueError('Current design copy mismatch')
    original[str(system/'SystemSummary.json')]=sha(system/'SystemSummary.json')
    if not re.search(r'\bmodule\s+e203_cpu_top\b',(inputs/'candidate.v').read_text()):raise ValueError('Wrong current system top')
    shared_db=Path(record['old_system'])/'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db'
    shared_lef=Path('/storage1/admin_public_dir/SRAM_Lib_2025/RAMSP4096X16/lef/RAMSP4096X16.lef')
    lef_paths=[Path(selection[k]) for k in ('std_lef','macro_lef')]+[shared_lef]
    infos=[lef_info(p.read_text()) for p in lef_paths]
    refs=structural_references((inputs/'candidate.v').read_text())
    allmacros={key:value for info in infos for key,value in info['macros'].items()}
    if not set(refs)<=set(allmacros):raise ValueError('Physical LEF does not cover new references: '+str(sorted(set(refs)-set(allmacros))))
    if not {'RAMSP1024X16','RAMSP4096X16'}<=set(refs):raise ValueError('Both current macro classes required')
    power=set();ground=set()
    for ref in refs:
        pins=allmacros[ref]['pins'];uses={v['use'] for v in pins.values()}
        if not {'POWER','GROUND'}<=uses:raise ValueError('Physical cell lacks PG definition: '+ref)
        power.update(k for k,v in pins.items() if v['use']=='POWER');ground.update(k for k,v in pins.items() if v['use']=='GROUND')
    if not power<=set(('VDD','VDDCE','VDDPE')) or not ground<=set(('VSS','VSSE')):raise ValueError('Unreviewed PG rail mapping')
    for path in lef_paths+[shared_db,Path(selection['technology']),Path(selection['tech_lef'])]:original[str(path)]=sha(path)
    ndms=[];snapshots={}
    for label in ('rvt','private'):
        src=old/('library_'+label)/(label+'.ndm');dest=out/('library_'+label)/(label+'.ndm')
        snapshots[str(src)]=tree(src);dest.parent.mkdir();shutil.copytree(str(src),str(dest))
        if tree(dest)!=snapshots[str(src)]:raise ValueError('NDM copy differs')
        ndms.append(dest)
    icc=Path(os.environ.get('ICC2_BIN') or physical['icc2']);lm=icc.with_name('icc2_lm_shell')
    if not icc.is_file() or not lm.is_file():raise ValueError('ICC2 and library manager required')
    shared=out/'library_shared';shared.mkdir();ndm=shared/'shared.ndm'
    cfg=scalar('PrTechnology',selection['technology'])+scalar('PrWorkspace','shared_1109')+scalar('PrDb',shared_db)+scalar('PrNdm',ndm)
    cfg+=tlist('PrLefs',[selection['tech_lef'],shared_lef]);(shared/'PrLibraryConfig.tcl').write_text(cfg)
    snapshot={'design_source':str(system),'top':'e203_cpu_top','frontend_commit':'c03eb048481b7d271dba54e518092c2eb9aa528f',
        'design_netlist_sha256':sha(inputs/'candidate.v'),'design_sdc_sha256':sha(inputs/'candidate.sdc'),
        'scope':'1109 CPU + NICE/TPU/DMA/ICB + 56 private/64 shared macros; external fixed peripherals excluded',
        'historical_source_usage':'physical technology and reference libraries only; old design nlib/DEF/netlist not imported',
        'inputs':original,'reference_snapshots':snapshots,'physical_used_references':refs,
        'lef_macro_sizes':{r:allmacros[r]['size_um'] for r in ('RAMSP1024X16','RAMSP4096X16')},
        'limitations':'initial placement only; RC/physical PG/CTS/routing/signoff pending'}
    save(out/'NewPrInputs.json',snapshot)
    print('CURRENT_DESIGN_SOURCE:',system,flush=True)
    print('CURRENT_NETLIST_SHA256:',snapshot['design_netlist_sha256'],flush=True)
    print('SCOPE: 1109 e203_cpu_top + private56/shared64; no old design reuse',flush=True)
    text=native(out,'shared_library',shared,lm,physical['lm_flag'],HERE/'PrLibrary.tcl',900)
    if 'REFERENCE_LIBRARY_CREATED_REVIEW_PENDING' not in text or not ndm.is_dir():raise ValueError('Shared NDM incomplete')
    ndms.append(ndm)
    stage=out/'design';stage.mkdir();lib=stage/'system_1109.nlib'
    cfg=''.join(scalar(k,v) for k,v in [('PrTechnology',selection['technology']),('PrDesignLib',lib),('PrNetlist',inputs/'candidate.v'),('PrSdc',inputs/'candidate.sdc')])
    cfg+=tlist('PrRefLibs',ndms)+tlist('PrPowerPins',sorted(power))+tlist('PrGroundPins',sorted(ground))
    cfg+=scalar('PrExpectedClockPeriod',serialized_clock((inputs/'candidate.sdc').read_text()))
    (stage/'CurrentConfig.tcl').write_text(cfg)
    text=native(out,'system_place',stage,icc,physical['icc2_flag'],HERE/'Place.tcl',1800)
    for name in ('system_1109.nlib','initial_floorplan.def','placed_1109.def','macros.tsv','core_bbox.txt'):
        if not (stage/name).exists():raise ValueError('Missing new physical result: '+name)
    if 'NEW_SYSTEM_INITIAL_PLACEMENT_NATIVE_COMPLETE' not in text:raise ValueError('Native placement completion missing')
    geometry(stage,out,snapshot['lef_macro_sizes'])
    verify(original)
    for src,digest in snapshots.items():
        if tree(Path(src))!=digest:raise ValueError('Historical reference library changed')
    (out/'OpenLayout.tcl').write_text('open_lib {'+str(lib)+'}\nopen_block e203_cpu_top\nstart_gui\n')
    save(out/'NewPrSummary.json',{'result':'NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING',
        'design_source':str(system),'design_netlist_sha256':snapshot['design_netlist_sha256'],
        'original_inputs_unchanged':True,'macro_count':120,'macro_bbox_overlap_count':0,
        'design_library':str(lib),'placed_def':str(stage/'placed_1109.def'),
        'limitations':'initial geometric placement; not standard-cell legalization/PG/RC/CTS/route/signoff acceptance'})
    print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
    print('LAYOUT_LIBRARY:',lib,flush=True)
    print('MACRO_SVG:',out/'MacroPlacement.svg',flush=True)
    print('OPEN_GUI:',str(icc)+' '+physical['icc2_flag']+' '+str(out/'OpenLayout.tcl'),flush=True)
    print('RESULT: NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING',flush=True)


if __name__=='__main__':
    try:main(Path(sys.argv[1]).resolve())
    except Exception as error:
        import traceback
        print('NEW_PR_ERROR:',error,flush=True);traceback.print_exc()
        print('RESULT: NEW_1109_SYSTEM_PR_INCOMPLETE; retain saved checkpoints',flush=True)
        raise SystemExit(2)
