"""Verify a frozen checkpoint and a clock-port-only SDC correction, retaining failures."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tarfile
from Prepare import check,sha

PORTS=('inspect_core_clk','core_csr_clk')
CLOCKS=('InspectCoreClock','CoreCsrClock')


def area_breakdown(out,expected):
    import csv
    with (out/'area_breakdown.tsv').open() as stream:
        rows=list(csv.DictReader(stream,delimiter='\t'))
    keys={'ACCELERATOR_LOGIC_AND_INTERFACES','ACCELERATOR_PRIVATE_SRAM','REUSED_CPU_AND_INTERNAL_ICB_LOGIC',
        'SHARED_ITCM_MACROS','SHARED_DTCM_MACROS','SHARED_TCM_BINDING_LOGIC','OTHER_SYSTEM_LOGIC'}
    if len(rows)!=len(keys) or {r['component'] for r in rows}!=keys: raise ValueError('Incomplete/disjoint area categories')
    areas={}
    for row in rows:
        value=float(row['area_um2'])
        if not (0<=value<1e12) or abs(float(row['area_mm2'])*1e6-value)>0.001: raise ValueError('Invalid area unit/value')
        if row['in_accelerator_budget']!=str(int(row['component'].startswith('ACCELERATOR_'))): raise ValueError('Invalid area budget class')
        areas[row['component']]=value
    counts={r['component']:int(r['leaf_count']) for r in rows}
    for key,count in (('ACCELERATOR_PRIVATE_SRAM',56),('SHARED_ITCM_MACROS',32),('SHARED_DTCM_MACROS',32)):
        if counts[key]!=count: raise ValueError('Wrong area macro inventory')
    total=sum(areas.values()); budget=areas['ACCELERATOR_LOGIC_AND_INTERFACES']+areas['ACCELERATOR_PRIVATE_SRAM']
    if abs(total-float(expected['SYSTEM_LIBRARY_AREA_UM2']))>0.01: raise ValueError('Area components do not match original system total')
    if abs(budget-703272.383184)>0.01 or abs(areas['ACCELERATOR_PRIVATE_SRAM']-512317.367184)>0.01:
        raise ValueError('Frozen accelerator area differs from verified original')
    return {'components':rows,'system_area_um2':total,'accelerator_budget_area_um2':budget,
        'accelerator_budget_limit_um2':2250000,'shared_capacity_bytes':524288,'private_capacity_bytes':114688,
        'scope':'Library cell/macro area; e203_cpu_top excluding external fixed peripherals; shared binding logic separately listed'}


def sdc_commands(text):
    text=text.replace('\\\n',' ')
    return Counter(' '.join(line.split()) for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#'))


def constraint_tokens(line):
    # No Tcl execution: recognize only literal one-port/clock collection expressions.
    return re.findall(r'\[(?:get_ports|get_clocks)\s+(?:\{[^{}]*\}|[^\]\s]+)\]|[^\s]+',line)


def literal_object(token,kind):
    match=re.fullmatch(r'\['+kind+r'\s+(?:\{([A-Za-z_][A-Za-z_0-9]*)\}|([A-Za-z_][A-Za-z_0-9]*))\]',token)
    if not match: raise ValueError('Expected literal single-object '+kind+': '+token)
    return match[1] or match[2]


def generated_clock(line):
    tokens=constraint_tokens(line); values={}; target=None; i=1
    while i<len(tokens):
        token=tokens[i]
        if token in ('-name','-source','-divide_by'):
            if token in values or i+1>=len(tokens): raise ValueError('Duplicate/incomplete clock option: '+line)
            values[token]=tokens[i+1]; i+=2
        elif token=='-combinational':
            if token in values: raise ValueError('Duplicate combinational option')
            values[token]=True; i+=1
        else:
            if target is not None: raise ValueError('Unexpected generated clock token: '+line)
            target=literal_object(token,'get_ports'); i+=1
    name=values.get('-name')
    if name not in CLOCKS or not values.get('-combinational') or float(values.get('-divide_by','1'))!=1:
        raise ValueError('Unexpected generated clock: '+line)
    if literal_object(values.get('-source',''),'get_ports')!='clk' or target!=PORTS[CLOCKS.index(name)]:
        raise ValueError('Unexpected generated clock source/target: '+line)
    return name


def forwarded_clock_budget(line):
    tokens=constraint_tokens(line); name=None; number=None; flags=set()
    for token in tokens[1:]:
        if token.startswith('[get_clocks '):
            if name is not None: raise ValueError('Multiple clock targets: '+line)
            name=literal_object(token,'get_clocks')
        elif token.startswith('-') and token in ('-setup','-hold','-rise','-fall','-min','-max'):
            if token in flags: raise ValueError('Duplicate budget flag')
            flags.add(token)
        else:
            if number is not None: raise ValueError('Unexpected clock budget token: '+line)
            number=float(token)
    expected=0.1
    if tokens[0]=='set_clock_uncertainty':
        if ('-setup' in flags)==('-hold' in flags): raise ValueError('Expected explicit setup or hold uncertainty')
        expected=0.2 if '-setup' in flags else 0.1
    elif flags.intersection({'-setup','-hold'}): raise ValueError('Invalid transition flag')
    if name not in CLOCKS or number is None or not abs(number-expected)<=1e-12:
        raise ValueError('Unexpected forwarded clock budget: '+line)


def budget_diff(before,after):
    old=sdc_commands(before); new=sdc_commands(after)
    removed=list((old-new).elements()); added=list((new-old).elements())
    seen_ports=set(); seen_clocks=set()
    for line in removed:
        match=re.fullmatch(r'set_output_delay\s+.*\[get_ports\s+(\{)?(inspect_core_clk|core_csr_clk)(?(1)\})\]',line)
        if not match: raise ValueError('Unexpected removed/changed constraint: '+line)
        seen_ports.add(match[2])
    for line in added:
        if line.startswith('create_generated_clock '):
            seen_clocks.add(generated_clock(line))
        elif line.startswith(('set_clock_uncertainty ','set_clock_transition ')):
            forwarded_clock_budget(line)
        else: raise ValueError('Unexpected added/changed constraint: '+line)
    if seen_ports!=set(PORTS) or seen_clocks!=set(CLOCKS): raise ValueError('Incomplete clock port correction')
    return {'removed_clock_output_data_delays':removed,'added_forwarded_clock_constraints':added,
        'all_other_serialized_constraints':'BYTE_TEXT_UNCHANGED_AFTER_WHITESPACE_NORMALIZATION'}


def prepare(source,out,tools):
    record=json.loads((source/'SystemBaseRecoveryInputs.json').read_text()); check(record)
    manifest=json.loads((source/'SystemMappingManifest.json').read_text())
    for name,digest in manifest.items():
        path=(source/name).resolve()
        if source not in path.parents or sha(path)!=digest: raise ValueError('System mapping report changed: '+name)
    summary=json.loads((source/'SystemBaseSummary.json').read_text())
    if summary['mapping_tool']!='COMPLETE' or summary['tcm_contract']!='PASS': raise ValueError('Incomplete system mapping')
    platform=Path(record['platform'])
    cpu=(platform/'core/e203_cpu.v').read_text()
    if not re.search(r'assign\s+inspect_core_clk\s*=\s*clk\s*;',cpu) or not re.search(r'assign\s+core_csr_clk\s*=\s*clk_core_exu\s*;',cpu):
        raise ValueError('Unexpected CPU clock output semantics')
    inputs=dict(record['inputs'])
    for name in manifest: inputs[str(source/name)]=sha(source/name)
    for path in (source/'SystemBaseRecoveryInputs.json',source/'SystemMappingManifest.json',source/'SystemBaseSummary.json',source/'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db'):
        inputs[str(path)]=sha(path)
    for path in tools.iterdir():
        if path.is_file(): inputs[str(path)]=sha(path)
    (out/'Inputs.json').write_text(json.dumps({'source':str(source),'inputs':inputs},indent=2)+'\n')
    print('CLOCK_PORT_INPUTS_VERIFIED: original checkpoint, reports, libraries and sources unchanged',flush=True)


def finish(out):
    record=json.loads((out/'Inputs.json').read_text()); check(record)
    log=(out/'dc.log').read_text(errors='replace')
    if 'CLOCK_PORT_REPORT_COMPLETE:' not in log or re.search(r'^(Error:|CLOCK_PORT_REPORT_ERROR:)',log,re.M):
        raise ValueError('Report-only tool completion missing/errors')
    data=dict(line.split(': ',1) for line in (out/'summary.txt').read_text().splitlines() if ': ' in line)
    original=json.loads((Path(record['source'])/'SystemBaseSummary.json').read_text())['mapped']
    area=area_breakdown(out,original)
    (out/'AreaBreakdown.json').write_text(json.dumps(area,indent=2)+'\n')
    for key,base in (('ORIGINAL_SETUP_WNS_NS','SETUP_WNS_NS'),('ORIGINAL_HOLD_WNS_NS','HOLD_WNS_NS')):
        if abs(float(data[key])-float(original[base]))>1e-7: raise ValueError('Reloaded checkpoint timing changed: '+key)
    for slack,status in (('SETUP_WNS_NS','SETUP_STATUS'),('HOLD_WNS_NS','HOLD_STATUS')):
        value=float(data[slack])
        if not (-1e20<value<1e20) or data[status]!=('PASS' if value>=0 else 'FAIL'): raise ValueError('Timing/status invalid')
    if data.get('NETLIST')!='UNCHANGED': raise ValueError('Missing immutable netlist proof')
    diff=budget_diff((out/'loaded.sdc').read_text(),(out/'clock_ports_corrected.sdc').read_text())
    (out/'ConstraintChanges.json').write_text(json.dumps(diff,indent=2)+'\n')
    data['DATA_BUDGETS_STATUS']='UNCHANGED_EXCEPT_TWO_CLOCK_OUTPUT_ROLES'
    (out/'ClockPortSummary.json').write_text(json.dumps(data,indent=2)+'\n')
    files=[p for p in sorted(out.iterdir()) if p.is_file() and p.suffix in ('.json','.rpt','.txt','.sdc','.log')
           and p.name!='runner.log' and not re.fullmatch(r'summary_recovery_v\d+_[A-Za-z0-9]+\.log',p.name)]
    (out/'MANIFEST.sha256').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in files))
    with tarfile.open(out/'ClockPortReports.partial.tar.gz','x:gz') as stream:
        for path in files+[out/'MANIFEST.sha256']: stream.add(path,arcname='ClockPortReview/'+path.name,recursive=False)
    for key in ('NETLIST','DATA_BUDGETS_STATUS','SETUP_WNS_NS','HOLD_WNS_NS','SETUP_STATUS','HOLD_STATUS'):
        print('CLOCK_PORT_REVIEW:',key,data[key])
    for row in area['components']:
        print('AREA_COMPONENT:',row['component'],'mm2='+row['area_mm2'],'budget='+row['in_accelerator_budget'])
    print('AREA_BUDGET_TOTAL_MM2:',format(area['accelerator_budget_area_um2']/1e6,'.9f'))
    print('SHARED_MEMORY: 512KiB = ITCM 256KiB + DTCM 256KiB; 64 RAMSP4096X16 macros')
    print('REPORT_ARCHIVE:',out/'ClockPortReports.partial.tar.gz')
    print('RESULT: CLOCK_PORT_REVIEW_COMPLETE (inspect timing statuses; TT ideal-clock only; system function/power pending)')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('mode',choices=('prepare','finish'))
    parser.add_argument('out',type=Path); parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.mode=='prepare': prepare(args.source.resolve(),args.out.resolve(),Path(__file__).resolve().parent)
    else: finish(args.out.resolve())
