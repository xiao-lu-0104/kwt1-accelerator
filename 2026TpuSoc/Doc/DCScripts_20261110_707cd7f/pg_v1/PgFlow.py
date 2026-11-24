"""Build and audit actual PG on an independent copy of the new grouped-IO design."""
import csv
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tarfile
from PrHelpers import native, save, scalar, sha, tlist, tree, verify
from PinPlan import validate as validate_io
from SystemFlow import REV, verify_manifest

HERE=Path(__file__).resolve().parent


def validate_geometry(stage):
    macros={}
    for row in csv.DictReader((stage/'macros.tsv').read_text().splitlines(),delimiter='\t'):
        name=row['instance'];coords=[float(row[k]) for k in ('x1','y1','x2','y2')]
        if name in macros or not all(math.isfinite(v) for v in coords):
            raise ValueError('Invalid macro inventory')
        macros[name]=(row['ref'],coords)
    if len(macros)!=120 or sum(v[0]=='RAMSP1024X16' for v in macros.values())!=56 or sum(v[0]=='RAMSP4096X16' for v in macros.values())!=64:
        raise ValueError('Expected private56/shared64 geometry')
    pins={n:set() for n in macros};counts={};widths=[]
    for row in csv.DictReader((stage/'MacroPgGeometry.tsv').read_text().splitlines(),delimiter='\t'):
        name=row['instance'];pin=row['pin']
        if name not in macros or row['ref']!=macros[name][0] or pin not in ('VDDCE','VDDPE','VSSE') or row['status']!='SHAPE_CAPTURED' or row['layers']!='M4':
            raise ValueError('Unreviewed or missing current macro PG shape: '+str(row))
        x1,y1,x2,y2=[float(row[k]) for k in ('x1','y1','x2','y2')]
        if not all(math.isfinite(v) for v in (x1,y1,x2,y2)) or x2<=x1 or y2<=y1:
            raise ValueError('Invalid PG shape bbox')
        if y2-y1<=x2-x1 or x2-x1>.28+1e-6:
            raise ValueError('Current PG shape is not a reviewed narrow M4 vertical long pin')
        a,b,c,d=macros[name][1]
        if x1<a-.001 or y1<b-.001 or x2>c+.001 or y2>d+.001:
            raise ValueError('PG shape lies outside native macro bbox')
        pins[name].add(pin);widths.append(x2-x1)
        key=row['ref']+'/'+pin;counts[key]=counts.get(key,0)+1
    if not widths or any(p!={'VDDCE','VDDPE','VSSE'} for p in pins.values()):
        raise ValueError('Every current macro must expose all three PG pins')
    return {'macros':120,'per_macro_all_three_pins':True,'shape_counts':counts,'shape_count':len(widths),
            'm4_pin_width_min_um':min(widths),'m4_pin_width_max_um':max(widths)}


def connectivity_result(text):
    if re.search(r'^\s*(Error:|Fatal:)',text,re.M):
        return {'clean':False,'reason':'native command errors retained'}
    labels={'wires':'wires','vias':'vias','stdcells':'standard_cells','standardcells':'standard_cells',
            'hardmacros':'hard_macros','iopads':'io_pads','iopadcells':'io_pads',
            'ioterminals':'io_terminals','hierarchicalblocks':'hierarchical_blocks','hierblocks':'hierarchical_blocks'}
    counts={k:[] for k in set(labels.values())};unknown=[]
    for line in text.splitlines():
        m=re.search(r'floating\s+(.+?)\s*[:=]\s*(\d+)\s*$',line,re.I)
        if m:
            label=re.sub('[^a-z]','',m.group(1).lower());key=labels.get(label)
            if key is None:unknown.append(line)
            else:counts[key].append(int(m.group(2)))
    complete=all(len(v)>=2 for v in counts.values()) and 'VDD' in text and 'VSS' in text
    return {'clean':bool(complete and not unknown and all(n==0 for v in counts.values() for n in v)),
            'counts':counts,'complete_vdd_vss_summaries':complete,'unknown_floating_lines':unknown,
            'scope':'all macro pins/all standard-cell pins; no IR/EM/package source acceptance'}


def drc_result(text):
    if re.search(r'^\s*(Error:|Fatal:)',text,re.M):
        return {'clean':False,'reason':'native command errors retained'}
    totals=[]
    for line in text.splitlines():
        if re.search(r'(total|number\s+of).*?(errors?|violations?|drcs?)',line,re.I):
            m=re.search(r'[:=]\s*(\d+)\s*$',line)
            if m:totals.append(int(m.group(1)))
    explicit=bool(re.search(r'\bno\s+(?:(?:pg|drc)\s+)*(?:errors?|violations?)\s+(?:has\s+been\s+|were\s+|was\s+)?found\b',text,re.I))
    return {'clean':bool((totals and all(n==0 for n in totals)) or (explicit and not any(totals))),
            'recognized_totals':totals,'explicit_no_errors':explicit,
            'scope':'native PG DRC only; not signal route DRC/LVS/IR/EM'}


def choose_source(soc,expected_manifest):
    choices=[]
    for p in soc.glob('tpusoc_initial_pr_v2_20261110_707cd7f_*'):
        f=p/'NewPrSummary.json'
        if not f.is_file():continue
        d=json.loads(f.read_text())
        if d.get('result')=='NEW_707CD7F_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING' and d.get('source_commit')==REV and d.get('original_inputs_unchanged') is True:
            choices.append((p,d))
    if len(choices)!=1:raise ValueError('Expected exactly one successful current grouped-IO source')
    source,summary=choices[0]
    verify_manifest(source,'PACKAGE.sha256',expected_manifest)
    if summary['io_validation']['status']!='NATIVE_IO_COORDINATES_MATCH_GROUPED_PLAN':raise ValueError('Unqualified IO source')
    if Path(summary['design_library']).resolve()!=(source/'design/system_707cd7f.nlib').resolve():raise ValueError('Unexpected source design path')
    return source,summary


def main(out):
    cfg=json.loads((out/'Config.json').read_text())
    source,summary=choose_source(Path.home()/'soc',cfg['initial_package_sha256'])
    for prior in (Path.home()/'soc').glob('tpusoc_pg_20261110_707cd7f_*/PgInputs.json'):
        if prior.parent.resolve()!=out.resolve() and json.loads(prior.read_text()).get('source_run')==str(source):
            raise ValueError('A PG attempt for this source already exists; inspect its checkpoint instead of rerunning: '+str(prior.parent))
    inputs=json.loads((source/'NewPrInputs.json').read_text());verify(inputs['inputs'])
    if (inputs['source_commit']!=REV or sha(source/'inputs/candidate.v')!=summary['design_netlist_sha256']
            or sha(source/'inputs/candidate.sdc')!=inputs['design_sdc_sha256']):
        raise ValueError('Current PG source identity differs')
    # The qualified source is read-only; validate_io writes a new report, so call it only on stage copies.
    geometry=validate_geometry(source/'design')
    save(out/'GeometryPrereview.json',geometry)
    originals=dict(inputs['inputs'])
    for name in ('NewPrSummary.json','NewPrInputs.json','PACKAGE.sha256','inputs/candidate.v','inputs/candidate.sdc',
                 'design/PinPlan.json','design/IoValidation.json','design/PortTerminalGeometry.tsv','design/MacroPgGeometry.tsv','design/macros.tsv'):
        originals[str(source/name)]=sha(source/name)
    expected_refs=inputs['reference_snapshots'];refs=[];source_refs={}
    for label in ('rvt','private','shared'):
        choices=[h for p,h in expected_refs.items() if Path(p).name==label+'.ndm']
        old=source/('library_'+label)/(label+'.ndm')
        if len(choices)!=1 or tree(old)!=choices[0]:raise ValueError('Current reference snapshot changed: '+label)
        dest=out/('library_'+label)/(label+'.ndm');dest.parent.mkdir();shutil.copytree(old,dest)
        if tree(dest)!=choices[0]:raise ValueError('Reference copy mismatch')
        refs.append(dest);source_refs[str(old)]=choices[0]
    original_lib=source/'design/system_707cd7f.nlib';original_snapshot=tree(original_lib)
    record={'source_commit':REV,'source_run':str(source),'source_design_snapshot':original_snapshot,
            'source_reference_snapshots':source_refs,'original_files':originals,'mesh_pitch_um':42,
            'macro_halo_um':1.12,'mesh_macro_blocked_layers':['M1','M2','M3','M4','M5'],
            'macro_connection':'M4 long pin to horizontal M5, requested 1x1 contact, then M6 mesh',
            'input_netlist_sha256':summary['design_netlist_sha256']}
    save(out/'PgInputs.json',record)
    period=inputs['expected_serialized_period_ns'];progress=[]
    previous=original_lib
    native_cfg=Path.home()/'soc/tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json'
    physical=json.loads(native_cfg.read_text());icc=Path(physical['icc2']);flag=physical['icc2_flag']
    originals[str(native_cfg)]=sha(native_cfg)
    print('SOURCE_COMMIT:',REV,flush=True);print('PG_SOURCE:',source,flush=True)
    print('GEOMETRY_PREREVIEW:',json.dumps(geometry,sort_keys=True),flush=True)

    def stage(kind,lib_source,script,limit):
        directory=out/kind;directory.mkdir()
        lib=directory/'system_707cd7f.nlib';before=tree(lib_source)
        shutil.copytree(lib_source,lib)
        if tree(lib)!=before or tree(lib_source)!=before:raise ValueError('Design checkpoint changed during copy; close only the new-layout GUI normally before retrying')
        text=''.join(scalar(k,v) for k,v in [('Phase',kind),('DesignLib',lib),('ExpectedPeriod',period)])+tlist('RefLibs',refs)
        (directory/'PgConfig.tcl').write_text(text)
        if kind in ('legalize','pg_core'):shutil.copy2(source/'design/PinPlan.json',directory/'PinPlan.json')
        (out/'OpenLastCheckpoint.tcl').write_text('open_lib {'+str(lib)+'}\nopen_block e203_cpu_top\nstart_gui\n')
        log=native(out,kind,directory,icc,flag,HERE/script,limit)
        return directory,lib,log

    for kind,tag in [('legalize','legalized'),('pg_core','pg_complete')]:
        directory,lib,log=stage(kind,previous,'PgStage.tcl',3600)
        if 'NEW_707CD7F_PG_PHASE_COMPLETE '+kind not in log or not (directory/(tag+'.def')).is_file():
            raise ValueError('Native stage not complete: '+kind)
        io=validate_io(directory)
        progress.append({'phase':kind,'complete':True,'library':str(lib),'io':io})
        save(out/'PgProgress.json',{'stages':progress});previous=lib
    checks={}
    # Run both checks even when the first report contains real violations or an unknown format.
    for kind,limit,parser in [('connectivity',1800,connectivity_result),('drc',3600,drc_result)]:
        try:
            directory,lib,log=stage(kind,previous,'PgCheck.tcl',limit)
            if 'NEW_707CD7F_PG_CHECK_EXECUTED '+kind not in log:raise ValueError('Missing native check completion')
            checks[kind]=parser((directory/(kind+'.rpt')).read_text())
            checks[kind]['executed']=True
        except Exception as e:
            checks[kind]={'clean':False,'executed':False,'error':str(e)}
        print('PG_CHECK_RESULT:',kind,json.dumps(checks[kind],sort_keys=True),flush=True)
        save(out/'PgChecks.json',checks)
    verify(originals)
    if tree(original_lib)!=original_snapshot:raise ValueError('Original new placement library changed')
    for p,h in source_refs.items():
        if tree(Path(p))!=h:raise ValueError('Original reference changed')
    clean=all(v.get('executed') is True and v.get('clean') is True for v in checks.values())
    result='NEW_707CD7F_PG_BUILT_CHECKS_PASS_ENGINEERING_REVIEW_PENDING' if clean else 'NEW_707CD7F_PG_BUILT_CHECKS_NOT_CLEAN_RETAIN_CHECKPOINTS'
    data={'result':result,'source_commit':REV,'source_run':str(source),'original_inputs_unchanged':True,
          'design_library':str(previous),'pg_def':str(out/'pg_core/pg_complete.def'),'checks':checks,
          'limitations':'initial legalization and PG engineering candidate; no CTS/signal route/RC/IR/EM/LVS/signoff; requested1x1 contact is not itself a via geometry proof'}
    save(out/'NewPgSummary.json',data)
    (out/'OpenPgLayout.tcl').write_text('open_lib {'+str(previous)+'}\nopen_block e203_cpu_top\nstart_gui\n')
    (out/'OpenPgDrc.tcl').write_text('open_lib {'+str(out/'drc/system_707cd7f.nlib')+'}\nopen_block e203_cpu_top\nstart_gui\n')
    print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
    print('OPEN_PG_GUI:',str(icc)+' '+flag+' '+str(out/'OpenPgLayout.tcl'),flush=True)
    print('RESULT:',result,flush=True)
    if not clean:raise ValueError('Inspect actual PG check reports; do not rerun the outer package')


if __name__=='__main__':
    out=Path(sys.argv[1]).resolve()
    try:main(out)
    except Exception as e:
        import traceback
        print('NEW_707CD7F_PG_ERROR:',e,flush=True);traceback.print_exc()
        print('RESULT: NEW_707CD7F_PG_INCOMPLETE_RETAIN_CHECKPOINTS',flush=True)
        raise SystemExit(2)
    finally:
        with tarfile.open(str(out/'PgReports.tar.gz'),'w:gz') as z:
            for p in sorted(out.rglob('*')):
                rel=p.relative_to(out)
                if any(part.endswith(('.nlib','.ndm')) for part in rel.parts) or rel.parts[0].startswith('library_') or p.name in ('payload.tar.gz','PgReports.tar.gz','runner.log'):continue
                if p.is_file():z.add(str(p),arcname=rel.as_posix())
