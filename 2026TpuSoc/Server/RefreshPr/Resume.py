"""Reuse the 1109 physical reference libraries after SDC serialization diagnosis."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import traceback
from Run import geometry,native,save,scalar,serialized_clock,sha,tlist,tree,verify

HERE=Path(__file__).resolve().parent


def pg_list(config,name):
    lines=[line for line in config.splitlines() if line.startswith('set '+name+' [list ')]
    if len(lines)!=1 or not re.fullmatch(r'set '+name+r' \[list (?:\{[A-Za-z0-9_]+\} ?)+\]',lines[0]):
        raise ValueError('Unexpected original reviewed PG list: '+name)
    return re.findall(r'\{([A-Za-z0-9_]+)\}',lines[0])


def main(out):
    soc=Path.home()/'soc';source=soc/'tpusoc_new_system_pr_20261109_b2ME75'
    record=json.loads((source/'NewPrInputs.json').read_text())
    if record['top']!='e203_cpu_top' or '20261109' not in Path(record['design_source']).name:
        raise ValueError('Only original 1109 full system is eligible')
    verify(record['inputs'])
    original=dict(record['inputs'])
    for name in ('NewPrInputs.json','design/CurrentConfig.tcl','design/system_place.log','library_shared/PrStatus.tsv'):
        original[str(source/name)]=sha(source/name)
    shared_status=(source/'library_shared/PrStatus.tsv').read_text()
    if 'REFERENCE_LIBRARY_CREATED_REVIEW_PENDING' not in shared_status:
        raise ValueError('Original shared reference NDM not successfully created')
    log=(source/'design/system_place.log').read_text(errors='replace')
    if 'New system core clock budget mismatch' not in log or 'UNBOUND_CELLS 0' not in log:
        raise ValueError('Expected the diagnosed clock-check failure after successful import')
    inputs=out/'inputs';inputs.mkdir()
    for name,key in [('candidate.v','design_netlist_sha256'),('candidate.sdc','design_sdc_sha256')]:
        p=source/'inputs'/name
        if sha(p)!=record[key]:raise ValueError('Original 1109 input copy changed: '+name)
        original[str(p)]=sha(p);shutil.copy2(str(p),str(inputs/name))
        if sha(inputs/name)!=record[key]:raise ValueError('Recovery input copy mismatch')
    period=serialized_clock((inputs/'candidate.sdc').read_text())
    print('CURRENT_DESIGN_SOURCE:',record['design_source'],flush=True)
    print('CURRENT_NETLIST_SHA256:',record['design_netlist_sha256'],flush=True)
    print('CLOCK_SERIALIZATION: target_ns=6.666667 serialized_ns='+period+'; original SDC unchanged',flush=True)
    snapshots={};ndms=[]
    for label in ('rvt','private','shared'):
        src=source/('library_'+label)/(label+'.ndm');dest=out/('library_'+label)/(label+'.ndm')
        snapshot=tree(src);snapshots[str(src)]=snapshot
        dest.parent.mkdir();shutil.copytree(str(src),str(dest))
        if tree(dest)!=snapshot:raise ValueError('Reference copy mismatch')
        ndms.append(dest)
    physical=json.loads((soc/'tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json').read_text())
    cfg=(source/'design/CurrentConfig.tcl').read_text()
    stage=out/'design';stage.mkdir();lib=stage/'system_1109.nlib'
    config=''.join(scalar(k,v) for k,v in [('PrTechnology',physical['selection']['technology']),('PrDesignLib',lib),
        ('PrNetlist',inputs/'candidate.v'),('PrSdc',inputs/'candidate.sdc'),('PrExpectedClockPeriod',period)])
    config+=tlist('PrRefLibs',ndms)+tlist('PrPowerPins',pg_list(cfg,'PrPowerPins'))+tlist('PrGroundPins',pg_list(cfg,'PrGroundPins'))
    (stage/'CurrentConfig.tcl').write_text(config)
    save(out/'PrRecoveryInputs.json',{'source':str(source),'design_source':record['design_source'],
        'design_netlist_sha256':record['design_netlist_sha256'],'design_sdc_sha256':record['design_sdc_sha256'],
        'expected_serialized_core_period_ns':period,'inputs':original,'reference_snapshots':snapshots,
        'tools':{str(p):sha(p) for p in HERE.iterdir() if p.is_file()},
        'scope':'same 1109 e203_cpu_top private56/shared64; no reference rebuild/DC/power rerun'})
    icc=Path(os.environ.get('ICC2_BIN') or physical['icc2'])
    text=native(out,'system_place',stage,icc,physical['icc2_flag'],HERE/'Place.tcl',1800)
    if 'NEW_SYSTEM_INITIAL_PLACEMENT_NATIVE_COMPLETE' not in text:raise ValueError('Native placement incomplete')
    for p in (lib,stage/'initial_floorplan.def',stage/'placed_1109.def'):
        if not p.exists():raise ValueError('Missing saved current physical result')
    geometry(stage,out,record['lef_macro_sizes'])
    verify(original)
    for src,snapshot in snapshots.items():
        if tree(Path(src))!=snapshot:raise ValueError('Original reference library changed')
    (out/'OpenLayout.tcl').write_text('open_lib {'+str(lib)+'}\nopen_block e203_cpu_top\nstart_gui\n')
    save(out/'NewPrSummary.json',{'result':'NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING',
        'source':str(source),'design_source':record['design_source'],'design_netlist_sha256':record['design_netlist_sha256'],
        'design_sdc_sha256':record['design_sdc_sha256'],'original_inputs_unchanged':True,
        'macro_count':120,'macro_bbox_overlap_count':0,'design_library':str(lib),'placed_def':str(stage/'placed_1109.def'),
        'limitations':'initial geometric placement; legal placement/RC/PG straps/CTS/route/signoff pending'})
    print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
    print('LAYOUT_LIBRARY:',lib,flush=True)
    print('OPEN_GUI:',str(icc)+' '+physical['icc2_flag']+' '+str(out/'OpenLayout.tcl'),flush=True)
    print('RESULT: NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING',flush=True)


if __name__=='__main__':
    try:main(Path(sys.argv[1]).resolve())
    except Exception as error:
        print('PR_RECOVERY_ERROR:',error,flush=True);traceback.print_exc()
        print('RESULT: NEW_1109_SYSTEM_PR_INCOMPLETE; retain checkpoints',flush=True)
        raise SystemExit(2)
