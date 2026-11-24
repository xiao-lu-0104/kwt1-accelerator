"""Prepare passive task SAIF collection on the frozen, passed mapped candidate."""
import argparse
import json
from pathlib import Path
import re
import shutil
from ReadProbe import sha
from PreparePower import fingerprints, select as select_inventory

SCOPE = 'SharedTest/Cpu/u_e203_cpu/u_e203_nice_core'


def select(previous):
    choices = [previous.resolve()] if previous else sorted(
        (Path.home()/'soc').glob('tpusoc_power_preflight_20261105_*'),
        key=lambda p:p.stat().st_mtime, reverse=True)
    for preflight in choices:
        try:
            record=json.loads((preflight/'PowerInputs.json').read_text())
            fingerprints(record)
            text=(preflight/'summary.txt').read_text()
            for required in ('NATIVE_SAIF_SMOKE: PASS', 'POWER_COMMANDS_AVAILABLE: True',
                             'AREA_PHYSICAL_UNIT: UM2_CONFIRMED_AGAINST_ALL_USED_REFERENCE_LEF'):
                if required not in text: raise ValueError('Preflight not ready: '+required)
            if 'RESULT: POWER_PREFLIGHT_COMPLETE' not in (preflight/'runner.log').read_text():
                raise ValueError('Preflight incomplete')
            inventory,_=select_inventory(Path(record['paths']['inventory']))
            return preflight, inventory, record
        except (OSError,ValueError,KeyError):
            if previous: raise
    raise ValueError('No unchanged, successful power preflight found')


def instrument(text):
    # Keep all original stimulus, comparisons, timing and handshake checks.
    if 'TaskActivity.' in text: raise ValueError('Task activity already instrumented')
    changes = {
        'Measured = 1; StartCycle = Cycles + 1;':
        'Measured = 1; StartCycle = Cycles + 1; TaskActivity.StartWindow();',
        'LastWriteCycle = Cycles; LastWritePending = 0;':
        'LastWriteCycle = Cycles; LastWritePending = 0; TaskActivity.EndRequested = 1;'
    }
    for before,after in changes.items():
        if text.count(before)!=1: raise ValueError('Unexpected activity boundary: '+before)
        text=text.replace(before,after)
    return text


def system_context(preflight, lines, out):
    catalog=json.loads((preflight/'SystemMemoryCatalog.json').read_text())
    result={'memory_catalog':catalog,'platform_files':[]}
    for line in lines:
        if not line or line.startswith(('+','-')): continue
        path=Path(line)
        if not any(key in path.name for key in ('e203_cpu_top','e203_cpu.v','e203_subsys',
                 'e203_srams','itcm_ram','dtcm_ram','gnrl_ram','sim_ram')): continue
        text=path.read_text(errors='replace')
        evidence=[s.strip() for s in text.splitlines() if re.search(
            r'module\s|DEPTH|AW\s*=|DW\s*=|\breg\s+\[|\bwire\s+\[|gnrl_ram|sim_ram|itcm|dtcm',s,re.I)]
        result['platform_files'].append({'path':str(path),'sha256':sha(path),'evidence':evidence[:100]})
    (out/'SystemPowerContext.json').write_text(json.dumps(result,indent=2)+'\n')
    print('SYSTEM_MEMORY_CATALOG_BEGIN')
    for item in catalog['available_sram_packages']:
        print('SRAM_PACKAGE:',item['directory'])
        for lib in item['tt_liberty'][:3]: print('SRAM_TT_LIB:',lib)
    print('SYSTEM_MEMORY_CATALOG_END')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    preflight,inventory,record=select(args.preflight)
    out=args.out.resolve()
    lines=(inventory/'full.f').read_text().splitlines()
    benches=[]
    for line in lines:
        if line and not line.startswith(('+','-')):
            path=Path(line)
            if re.search(r'\bmodule\s+SharedTest\s*;',path.read_text(errors='replace')): benches.append(path)
    if len(benches)!=1: raise ValueError('Expected one original strict SharedTest')
    source=benches[0].read_text()
    for required in ('UNKNOWN_LOADER_COMMAND_READY','UNKNOWN_LOADER_RESPONSE_VALID',
                     'UNKNOWN_LOADER_READ_DATA','Result !== ExpectedHost[WordIndex]'):
        if required not in source: raise ValueError('Strict/golden guard missing: '+required)
    bench=out/'TaskSharedTest.sv'
    bench.write_text(instrument(source))
    netlist=out/'candidate.v'
    shutil.copy2(inventory/'candidate.v',netlist)
    if sha(netlist)!=record['paths']['candidate_sha256']: raise ValueError('Candidate changed')
    lines=[str(bench) if line==str(benches[0]) else str(netlist)
           if line==str(inventory/'candidate.v') else line for line in lines]
    (out/'Task.f').write_text('\n'.join(lines)+'\n')
    shutil.copy2(inventory/'GateResetInventory.sv',out/'GateResetInventory.sv')
    for name in ('IcbMirror.sv','GateWatch.sv'):
        if sha(inventory/'tools'/name)!=sha(Path(__file__).parent/name):
            raise ValueError('Passed passive observer differs from packaged source: '+name)
        shutil.copy2(inventory/'tools'/name,out/name)
    for name in ('Bundle.txt','Functional.txt'):
        shutil.copy2(inventory/name,out/name)
    tracked=dict(record['inputs'])
    for path in [preflight/name for name in ('summary.txt','runner.log','Paths.json','PowerInputs.json',
            'SystemMemoryCatalog.json','LibraryEvidence.json')]+[inventory/'GateResetInventory.sv']+benches:
        tracked[str(path)]=sha(path)
    for path in [out/name for name in ('candidate.v','TaskSharedTest.sv','Task.f','GateResetInventory.sv',
            'IcbMirror.sv','GateWatch.sv')]: tracked[str(path)]=sha(path)
    for path in Path(__file__).parent.iterdir():
        if path.is_file(): tracked[str(path)]=sha(path)
    # Fingerprint every directly referenced HDL/library file, not only its file list.
    for line in lines:
        if line.startswith('-v '): path=Path(line[3:])
        elif line and not line.startswith(('+','-')): path=Path(line)
        else: continue
        tracked[str(path)]=sha(path)
    (out/'TaskPowerInputs.json').write_text(json.dumps({'preflight':str(preflight),
        'inventory':str(inventory),'paths':record['paths'],'scope':SCOPE,'inputs':tracked,
        'initial_condition':'pattern2; one reset clock; release before reset deassertion',
        'window':'first input request falling edge through falling edge after final output response',
        'simulation_period_ns':6.667,'constraint_period_ns':6.666667},indent=2)+'\n')
    for name in ('Ddc.txt','StdDb.txt','SpDb.txt'):
        shutil.copy2(preflight/name,out/name)
    system_context(preflight,lines,out)
    print('VERIFIED_PREFLIGHT:',preflight)
    print('FROZEN_INVENTORY:',inventory)
    print('MATCHED_CANDIDATE_SHA256:',sha(netlist))
    print('ACTIVITY_SCOPE:',SCOPE,'; accelerator+private SRAM only')
    print('TASK_WINDOW: complete counted cycles, including shared input/parameter loading; excludes init/result comparison')


if __name__=='__main__': main()
