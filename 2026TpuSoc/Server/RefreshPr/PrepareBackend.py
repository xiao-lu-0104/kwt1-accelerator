"""Snapshot the successful 1109 placement and collect installed backend/RC evidence."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback
from Run import native,save,scalar,sha,tlist,tree,verify

HERE=Path(__file__).resolve().parent


def map_inventory(root,limit=45,max_files=20000):
    started=time.monotonic();found=[];count=0;truncated=False
    for parent,dirs,names in os.walk(str(root),followlinks=False):
        dirs[:]=sorted(d for d in dirs if not d.endswith(('.ndm','.nlib')) and not (Path(parent)/d).is_symlink())
        if time.monotonic()-started>limit:truncated=True;break
        for name in sorted(names):
            count+=1
            if count>max_files:truncated=True;break
            low=name.lower();p=Path(parent)/name
            if not p.is_symlink() and (low.endswith(('.map','.layermap','.layer_map')) or 'tech2itf' in low):
                if p.stat().st_size<=1024*1024:
                    found.append({'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,
                        'preview':p.read_bytes()[:12000].decode(errors='replace')})
        if truncated:break
    return {'root':str(root),'files_seen':count,'truncated':truncated,'candidates':found}


def choose(soc):
    good=[]
    for p in soc.glob('tpusoc_system_pr_resume_20261109_*'):
        if (p/'NewPrSummary.json').is_file():
            value=json.loads((p/'NewPrSummary.json').read_text())
            if value.get('result')=='NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING' and value.get('original_inputs_unchanged') is True:
                good.append((p,value))
    if len(good)!=1:raise ValueError('Expected one successful 1109 full-system placement, found '+str(len(good)))
    return good[0]


def main(out):
    soc=Path.home()/'soc';source,summary=choose(soc)
    record=json.loads((source/'PrRecoveryInputs.json').read_text());verify(record['inputs'])
    system=Path(summary['design_source'])
    if '20261109' not in system.name or sha(system/'mapped/candidate.v')!=summary['design_netlist_sha256']:
        raise ValueError('Successful placement is not the unchanged 1109 system candidate')
    if sha(system/'mapped/candidate.sdc')!=summary['design_sdc_sha256']:raise ValueError('Current system SDC changed')
    bound=dict(record['inputs'])
    for n in ('NewPrSummary.json','PrRecoveryInputs.json','design/placed_1109.def','design/system_place.log','MacroGeometry.json'):
        bound[str(source/n)]=sha(source/n)
    libraries={};copies={}
    pairs=[('design/system_1109.nlib',source/'design/system_1109.nlib')]
    pairs += [('library_'+n+'/'+n+'.ndm',source/('library_'+n)/(n+'.ndm')) for n in ('rvt','private','shared')]
    for relative,original in pairs:
        libraries[str(original)]=tree(original);dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(str(original),str(dest))
        if tree(dest)!=libraries[str(original)]:raise ValueError('Library copy mismatch: '+relative)
        copies[relative]=str(dest)
    physical_path=soc/'tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json'
    physical=json.loads(physical_path.read_text());verify(physical['inputs'])
    preflight=Path(physical['preflight'])/'BackendPreflight.json'
    assets=json.loads(preflight.read_text())['assets'];selection=physical['selection']
    root=Path(selection['std_root']).resolve()
    rc=[]
    for asset in assets:
        p=Path(asset['path'])
        if p.suffix.lower() in ('.tluplus','.tlu_plus') and root in p.resolve().parents:
            entry={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,
                'matches_selected_stack_name':'1p8m_1tm' in p.name.lower() or '8lm_1tm' in p.name.lower()}
            with p.open('rb') as f:head=f.read(16000)
            # This is a header preview, not an assertion of physical compatibility.
            entry['header_preview']=''.join(c if c in '\n\t\r' or 32<=ord(c)<127 else '?' for c in head.decode(errors='replace'))[:3000]
            rc.append(entry);bound[str(p)]=entry['sha256']
    mappings=map_inventory(root)
    for value in mappings['candidates']:bound[value['path']]=value['sha256']
    bound[str(physical_path)]=sha(physical_path);bound[str(preflight)]=sha(preflight)
    save(out/'RcInventory.json',{'selected_technology':selection['technology'],'selected_tech_lef':selection['tech_lef'],
        'selected_stack':'RVT 8lm_1tm','rc_candidates':rc,'map_inventory':mappings,
        'acceptance':'inventory only; no candidate chosen until layer/corner/native compatibility checked'})
    stage=out/'design'
    cfg=scalar('PrDesignLib',stage/'system_1109.nlib')+tlist('PrRefLibs',[out/('library_'+n)/(n+'.ndm') for n in ('rvt','private','shared')])
    (stage/'BackendProbeConfig.tcl').write_text(cfg)
    save(out/'BackendPrepareInputs.json',{'source':str(source),'design_source':str(system),
        'design_netlist_sha256':summary['design_netlist_sha256'],'design_sdc_sha256':summary['design_sdc_sha256'],
        'inputs':bound,'source_library_snapshots':libraries,'copies':copies,'scope':'1109 e203_cpu_top private56/shared64',
        'rc_status':'not selected; installed manual and mapping audit',
        'tools':{str(p):sha(p) for p in HERE.iterdir() if p.is_file()}})
    print('SOURCE_1109_PLACEMENT:',source,flush=True)
    print('CURRENT_NETLIST_SHA256:',summary['design_netlist_sha256'],flush=True)
    print('INSPECTION_SCOPE: independent design/reference copies; no PG/place_opt/CTS/route yet',flush=True)
    icc=Path(os.environ.get('ICC2_BIN') or physical['icc2'])
    text=native(out,'backend_probe',stage,icc,physical['icc2_flag'],HERE/'BackendProbe.tcl',600)
    if 'BACKEND_PROBE_NATIVE_COMPLETE' not in text:raise ValueError('Installed backend audit incomplete')
    verify(bound)
    for name,snapshot in libraries.items():
        if tree(Path(name))!=snapshot:raise ValueError('Original successful layout/reference library changed')
    save(out/'BackendPrepareSummary.json',{'result':'NEW_1109_BACKEND_PREPARATION_COMPLETE',
        'source':str(source),'design_source':str(system),'source_unchanged':True,
        'scope':'preparation only; source-copy, native placement/technology/command evidence collected',
        'backend_implementation':'PG/place_opt/CTS/route not run in this preparation stage'})
    print('\n=== ROUTING_LAYERS_AND_PLACEMENT ===',flush=True)
    print((stage/'BackendOverview.txt').read_text(),flush=True)
    print('=== MATCHING_STACK_RC_CANDIDATES ===',flush=True)
    matching=[entry for entry in rc if entry['matches_selected_stack_name']]
    for entry in matching:print('RC_CANDIDATE:',entry['path'],flush=True)
    print('RC_COUNTS: all='+str(len(rc))+' stack_name_matches='+str(len(matching)),flush=True)
    print('=== LAYER_MAPPING_CANDIDATES ===',flush=True)
    for entry in mappings['candidates'][:12]:
        print('MAP_CANDIDATE:',entry['path'],flush=True)
        print(entry['preview'][:1200],flush=True)
    print('MAP_TOTAL:',len(mappings['candidates']),flush=True)
    print('MAP_SCAN: files='+str(mappings['files_seen'])+' truncated='+str(mappings['truncated']),flush=True)
    print('=== INSTALLED_BACKEND_SYNTAX ===',flush=True)
    print((stage/'BackendKeySyntax.txt').read_text(),flush=True)
    print('ORIGINAL_LAYOUT_UNCHANGED: True',flush=True)
    print('RESULT: NEW_1109_BACKEND_PREPARATION_COMPLETE',flush=True)


if __name__=='__main__':
    try:main(Path(sys.argv[1]).resolve())
    except Exception as error:
        print('BACKEND_PREPARE_ERROR:',error,flush=True);traceback.print_exc()
        print('RESULT: NEW_1109_BACKEND_PREPARATION_INCOMPLETE',flush=True)
        raise SystemExit(2)
