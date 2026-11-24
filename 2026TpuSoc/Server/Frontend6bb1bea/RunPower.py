"""Current frozen accelerator -> mapped SysBus32 system -> cold-task SAIF/power."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from NativeHelpers import load,save,sha,native,tcl
from power_summary import power_values,group_values

REV='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6'
DC='/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell'

def verify(root,manifest):
    for n,h in manifest['files_sha256'].items():
        if sha(root/n)!=h:raise ValueError('Input changed: '+str(root/n))

def write_config(where,pdk,values):
    lines=['set StdDb '+tcl(pdk['stdcell_db']),
           'set SramDbs [list '+' '.join(tcl(p) for p in pdk['sram_dbs'])+']']
    for k,v in values.items():
        lines.append('set '+k+' '+('[list '+' '.join(tcl(p) for p in v)+']' if isinstance(v,list) else tcl(v)))
    (where/'Config.tcl').write_text('\n'.join(lines)+'\n')

def text_model(p):
    return (gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()).decode(errors='replace')

def definitions(text):
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
    return set(re.findall(r'\b(?:module|primitive)\s+(?:automatic\s+)?(\w+)',text))

def foundry_models(root,cache,pdk,required):
    folder=root/'models';folder.mkdir(exist_ok=True)
    ledger=load(cache/'Cache.json')['libraries']
    records=[r for r in ledger if r.get('cached')==pdk['stdcell_db']]
    roots=[]
    if os.environ.get('TPU_STDCELL_VERILOG'):
        roots += [Path(p) for p in os.environ['TPU_STDCELL_VERILOG'].split(os.pathsep)]
    roots += [Path(r['source']).parents[2] for r in records]
    roots += [Path(pdk['stdcell_db']).parents[2]] if not roots else []
    paths=set()
    for search in roots:
        if search.is_file():paths.add(search)
        elif search.is_dir():
            for pattern in ('*.v','*.v.gz','*.sv','*.sv.gz'):paths.update(search.rglob(pattern))
    candidates={p:definitions(text_model(p)) for p in sorted(paths)}
    missing=set(required)-{'RAMSP1024X16','RAMSP4096X16','**logic_0**','**logic_1**'}
    selected=[]
    while missing:
        useful=[p for p,refs in candidates.items() if refs & missing]
        if not useful:raise ValueError('Missing real standard-cell Verilog models: '+repr(sorted(missing)[:30])+'; searched '+repr(roots))
        p=sorted(useful,key=lambda p:(-len(candidates[p]&missing),len(str(p)),str(p)))[0]
        selected.append(p);missing-=candidates.pop(p)
    covered=set().union(*(definitions(text_model(p)) for p in selected))
    for p,refs in candidates.items():
        if re.search(r'\bprimitive\s+\w+',text_model(p)) and refs-covered:
            selected.append(p);covered|=refs
    vendor=Path('/storage1/admin_public_dir/SRAM_Lib_2025')
    for ref in ('RAMSP1024X16','RAMSP4096X16'):
        p=vendor/ref/'verilog'/(ref+'.v')
        if not p.is_file():raise ValueError('Missing vendor macro model '+str(p))
        selected.append(p)
    copied=[];inputs={}
    for i,p in enumerate(selected):
        q=folder/(str(i)+'_'+p.name.removesuffix('.gz') if hasattr(str,'removesuffix') else str(i)+'_'+re.sub(r'\.gz$','',p.name))
        q.write_text(text_model(p));copied.append(q);inputs[str(p)]=sha(p)
    save(root/'ModelInputs.json',{'original_sha256':inputs,'copied_sha256':{str(p):sha(p) for p in copied}})
    return copied,selected

def sv_path(path):
    return '.'.join(p if re.fullmatch(r'[A-Za-z_]\w*',p) else '\\'+p+' ' for p in path.split('/'))

def memory_array(model,ref):
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text_model(model),flags=re.S)
    m=re.search(r'\bmodule\s+'+ref+r'\b.*?\bendmodule\b',text,re.S)
    if not m:raise ValueError('Missing macro definition '+ref)
    arrays=re.findall(r'\b(?:reg|logic)\s*\[[^\]]+\]\s*(\w+)\s*\[[^\]]+\]',m[0])
    preferred=[n for n in arrays if n.lower() in ('mem','memory','words','ram','mem_array')]
    if len(preferred)==1:return preferred[0]
    if len(arrays)==1:return arrays[0]
    raise ValueError('Review actual vendor memory array names for '+ref+': '+repr(arrays))

def hex_words(p,b,width):
    assert len(b)%width==0
    p.write_text(''.join(format(int.from_bytes(b[i:i+width],'little'),'0%dx'%(2*width))+'\n' for i in range(0,len(b),width)))

def initialize(root,task,cells,models):
    directory=root/task;directory.mkdir(exist_ok=True)
    firmware=(root/'firmware'/(task+'.bin')).read_bytes()
    expected_boot=b''.join(((r<<7)|0x13).to_bytes(4,'little') for r in range(1,32))
    if not firmware.startswith(expected_boot):raise ValueError('Missing executable CPU GPR clears')
    if len(firmware)>65536:raise ValueError('Firmware exceeds current 64KiB ITCM')
    firmware+=bytes(65536-len(firmware))
    image=directory/'firmware32.hex';hex_words(image,firmware,4)
    lines=['`timescale 1ns/1fs','module MemoryInit;','bit Done=0,Released=0;',
           'logic Active=0,ReadMode=0;','logic [11:0] Address=0;',
           'wire SmallCen=!(Active && Address<1024);','wire LargeCen=!Active;',
           'logic [31:0] CodeAddress=0;','logic [31:0] CodeData=0;',
           "wire [7:0] CodeMask=CodeAddress[2] ? 8'hf0 : 8'h0f;",
           'logic [31:0] Firmware[0:16383];','integer Word;']
    forces=[];releases=[];checks=[];count={};itcm_pairs=set();itcm_scopes={}
    for name,ref in cells.items():
        if ref not in ('RAMSP1024X16','RAMSP4096X16'):continue
        count[ref]=count.get(ref,0)+1
        depth=1024 if ref=='RAMSP1024X16' else 4096
        if name.startswith('Itcm/'):
            bank=re.search(r'BanksLoop(?:\[|_)(\d+)',name)
            lane=re.search(r'Lanes(?:\[|_)(\d+)',name)
            if not bank or not lane:raise ValueError('Review mapped ITCM bank/lane name '+name)
            bank,lane=int(bank[1]),int(lane[1]);itcm_pairs.add((bank,lane))
            itcm_scopes[(bank,lane)]='PowerTest.Dut.'+sv_path(name)
        scope='PowerTest.Dut.'+sv_path(name)
        for pin,rhs in [('CEN','SmallCen' if depth==1024 else 'LargeCen'),('GWEN','ReadMode'),('WEN',"16'b0"),
                        ('A','Address[9:0]' if depth==1024 else 'Address'),('D',"16'b0")]:
            forces.append('force '+scope+'.'+pin+'='+rhs+';')
            releases.append('release '+scope+'.'+pin+';')
        label=json.dumps('PHYSICAL_INIT_READBACK_FAILED '+name+' word=%0d actual=%h expected=%h')
        checks.append('if(Word<'+str(depth)+' && '+scope+'.Q !== 16\'b0) $fatal(1,'+label+',Word,'+scope+'.Q,16\'b0);')
    if count!={'RAMSP1024X16':56,'RAMSP4096X16':80} or itcm_pairs!={(b,l) for b in range(2) for l in range(4)}:
        raise ValueError('Incomplete memory initialization inventory '+repr(count))
    lines+=['initial begin',
            '$readmemh('+json.dumps(str(image))+',Firmware,0,16383);',
            'for(integer I=0;I<16384;I++) if($isunknown(Firmware[I])) $fatal(1,"Unknown firmware image");',
            'repeat(12) @(negedge PowerTest.Clock);']+forces
    lines+=['for(Word=0;Word<4096;Word++) begin',
            '  @(negedge PowerTest.Clock);Active=1;ReadMode=0;Address=12\'(Word);',
            '  @(posedge PowerTest.Clock);#1.5;','end',
            'for(Word=0;Word<4096;Word++) begin',
            '  @(negedge PowerTest.Clock);ReadMode=1;Address=12\'(Word);',
            '  @(posedge PowerTest.Clock);#1.5;']+checks+['end',
            '@(negedge PowerTest.Clock);Active=0;']+releases+[
            # Use the real ITCM wrapper's 32-bit write masks. Its 64-bit D
            # bus repeats the same 32-bit CPU word; forcing separate lane
            # pins with different values would conflict on collapsed nets.
            'force PowerTest.Dut.Itcm.RequestValid=1;',
            'force PowerTest.Dut.Itcm.RequestReady=1;',
            'force PowerTest.Dut.Itcm.ReadEnable=ReadMode;',
            'force PowerTest.Dut.Itcm.Address=CodeAddress;',
            'force PowerTest.Dut.Itcm.WriteData={CodeData,CodeData};',
            'force PowerTest.Dut.Itcm.WriteMask=CodeMask;',
            'for(Word=0;Word<16384;Word++) begin',
            "  @(negedge PowerTest.Clock);ReadMode=0;CodeAddress=32'(Word*4);CodeData=Firmware[Word];",
            '  @(posedge PowerTest.Clock);#1.5;','end',
            'for(Word=0;Word<16384;Word++) begin',
            "  @(negedge PowerTest.Clock);ReadMode=1;CodeAddress=32'(Word*4);",
            '  @(posedge PowerTest.Clock);#1.5;']
    for bank in range(2):
        for half in range(2):
            value='{'+itcm_scopes[(bank,half*2+1)]+'.Q,'+itcm_scopes[(bank,half*2)]+'.Q}'
            lines.append('if(Word/8192=='+str(bank)+' && Word%2=='+str(half)+' && '+value+' !== Firmware[Word]) $fatal(1,"ITCM_CODE_PIN_READBACK_FAILED word=%0d actual=%h expected=%h",Word,'+value+',Firmware[Word]);')
    lines+=['end','@(negedge PowerTest.Clock);',
            'release PowerTest.Dut.Itcm.RequestValid;','release PowerTest.Dut.Itcm.RequestReady;',
            'release PowerTest.Dut.Itcm.ReadEnable;','release PowerTest.Dut.Itcm.Address;',
            'release PowerTest.Dut.Itcm.WriteData;','release PowerTest.Dut.Itcm.WriteMask;',
            'Released=1;Done=1;',
            '$display("PHYSICAL_MEMORY_PIN_INIT_READBACK_PASS: 136 macros; firmware only in ITCM; shared/private/DTCM zero; all forces released before CPU startup");',
            '$display("MEMORY_INIT_DONE firmware_only_in_ITCM shared_and_private_zero_no_task_weights");','end',
            'always @(posedge PowerTest.ResetN) if(!Done || !Released) $fatal(1,"CPU reset released before physical init/release");','endmodule']
    (directory/'MemoryInit.sv').write_text('\n'.join(lines)+'\n')
    for n in ('source','expected'):hex_words(directory/(n+'.hex'),(root/'vectors'/task/(n+'.bin')).read_bytes(),4)
    return directory

def check_saif(saif,seconds):
    with saif.open(errors='replace') as f:head=f.read(32768)
    ts=re.search(r'\(TIMESCALE\s+([\d.eE+-]+)\s+(fs|ps|ns|us|ms|s)\s*\)',head)
    duration=re.search(r'\(DURATION\s+([\d.eE+-]+)\s*\)',head)
    if not ts or not duration:raise ValueError('Missing native SAIF time header')
    actual=float(ts[1])*float(duration[1])*{'fs':1e-15,'ps':1e-12,'ns':1e-9,'us':1e-6,'ms':1e-3,'s':1}[ts[2]]
    if abs(actual-seconds)>max(1e-12,seconds*1e-6):raise ValueError('SAIF/task measurement window mismatch')
    unknown_entries=0;switching=False;regions={key:False for key in ['Backend','Accelerator','Shared','Itcm','Dtcm']}
    with saif.open(errors='replace') as f:
        for line in f:
            unknown_entries+=sum(float(v)>0 for v in re.findall(r'\(TX\s+([\d.eE+-]+)\)',line))
            switching |= bool(re.search(r'\(TC\s+[1-9]',line))
            for key in regions:
                if re.search(r'\(INSTANCE\s+'+key+r'(?:\s|\))',line):regions[key]=True
    if not switching or not all(regions.values()):raise ValueError('Missing SAIF switching/system regions '+repr(regions))
    return {'TX_nonzero_entries':unknown_entries,'regions':regions,'seconds':actual}

def main():
    root=Path(sys.argv[1]).resolve();tools=root/'tools';uid=str(os.getuid())
    manifest=load(root/'PowerManifest.json')
    if manifest['source_commit']!=REV:raise ValueError('Wrong power package source')
    verify(root,manifest)
    accroot=Path('/tmp/final_dc_6bb1bea_'+uid)
    accepted=[p for p in (accroot/'hold_accelerator',accroot/'dc_accelerator') if (p/'Accepted.json').is_file()]
    if len(accepted)!=1:raise ValueError('Expected one accepted current accelerator candidate')
    acc=accepted[0];evidence=load(acc/'Accepted.json')
    if evidence['source_commit']!=REV or sha(acc/'candidate.v')!=evidence['netlist_sha256']:raise ValueError('Frozen accelerator source/netlist mismatch')
    original=load(accroot/'SourceManifest.json');verify(accroot,original)
    backend_bytes=(accroot/'source/Backend/E203TpuBackend.sv').read_bytes()
    backend_sha=hashlib.sha256(backend_bytes.replace(b'\r\n',b'\n')).hexdigest()
    if backend_sha!=manifest['original_backend_sha256']:raise ValueError('System adapter belongs to another backend')
    cache=Path('/tmp/final_7cf5155_pdk_'+uid);pdk=load(cache/'Pdk.json')
    if not (cache/'NativeCacheReady.txt').is_file():raise ValueError('Reusable cache verification marker missing')
    for p in [pdk['stdcell_db']]+pdk['sram_dbs']:
        if not Path(p).is_file():raise ValueError('Cached library unavailable '+p)
        records=[r for r in load(cache/'Cache.json')['libraries'] if r.get('cached')==p]
        if not records or any(r['sha256']!=sha(Path(p)) for r in records):raise ValueError('Cached library checksum mismatch '+p)
    system=root/'system';system.mkdir(exist_ok=True)
    sources=[root/'cpu'/p for p in manifest['cpu_sources']]
    sources += [root/'integration/TpuResetSync.sv',root/'integration/FrozenBackend.sv',tools/'PhysicalMemory.sv',root/'integration/SystemPhysical.sv']
    write_config(system,pdk,{'Includes':[root/'cpu/rtl/e203/core'],'Sources':sources,
        'AcceleratorDdc':acc/'candidate.ddc','Common':tools/'AsicCommon.tcl','Constraints':tools/'Constraints.tcl'})
    print('FROZEN_ACCELERATOR='+str(acc),flush=True)
    print('POWER_CONFIGURATION: 16 MAC, 150MHz, cold single tasks, original ICB32; 56 private + 64 shared + 16 TCM macros',flush=True)
    if not (system/'Complete.json').is_file():
        native([DC,'-f',str(tools/'System.tcl')],system,'NEW_6BB1BEA_SYSTEM_MAPPED')
        data=dict(line.split('\t',1) for line in (system/'Metrics.tsv').read_text().splitlines())
        # Retain any system timing violation explicitly; zero-delay activity
        # power remains an estimate and cannot establish timing closure.
        save(system/'Complete.json',{'source_commit':REV,'netlist_sha256':sha(system/'candidate.v'),
             'metrics':data,'timing_pass':min(float(data['setup_wns_ns']),float(data['hold_wns_ns']))>=0})
    current=load(system/'Complete.json')
    if current['source_commit']!=REV or sha(system/'candidate.v')!=current['netlist_sha256']:raise ValueError('System candidate changed')
    print('CURRENT_SYSTEM_METRICS: '+json.dumps(current['metrics'],sort_keys=True),flush=True)
    if not current['timing_pass']:print('SYSTEM_TIMING_VIOLATIONS_RETAINED: zero-delay power is an estimate; 150MHz system timing is not closed',flush=True)
    cells=dict(line.split('\t',1) for line in (system/'cells.tsv').read_text().splitlines())
    models,original_models=foundry_models(root,cache,pdk,set(cells.values()))
    vcs=shutil.which('vcs')
    if not vcs:
        choices=sorted(Path('/eda/synopsys/vcs').glob('*/bin/vcs'))
        if choices:vcs=str(choices[-1])
    if not vcs:raise ValueError('VCS executable missing; set PATH to installed VCS')
    summaries=[]
    for task in ('ff1','encoder'):
        directory=initialize(root,task,cells,original_models)
        f=[str(system/'candidate.v'),str(tools/'PowerTest.sv'),str(directory/'MemoryInit.sv')]
        for copied,original_model in zip(models,original_models):f+=['-v '+str(copied),'+incdir+'+str(original_model.parent)]
        (directory/'Gate.f').write_text('\n'.join(f)+'\n')
        compile_dir=directory/'compile';compile_dir.mkdir(exist_ok=True)
        if not (compile_dir/'Complete.json').is_file():
            command=[vcs,'-full64','-sverilog','-debug_access+all','-timescale=1ns/1ps','+notimingcheck','+nospecify','+delay_mode_zero','+vcs+saif_libcell',
                     '-f',str(directory/'Gate.f'),'-top','PowerTest','-o',str(directory/'simv')]
            # VCS provides no universal completion marker; append one only
            # after its successful exit and generated executable check.
            script=compile_dir/'Compile.py'
            script.write_text('import os,subprocess\ncmd='+repr(command)+'\nsubprocess.check_call(cmd)\nassert os.access('+repr(str(directory/'simv'))+',os.X_OK)\nprint("CURRENT_GATE_COMPILE_COMPLETE")\n')
            native(['python3',str(script)],compile_dir,'CURRENT_GATE_COMPILE_COMPLETE')
            save(compile_dir/'Complete.json',{'system_netlist_sha256':current['netlist_sha256']})
        if not (directory/'Activity.json').is_file():
            native([str(directory/'simv'),'+TASK='+task,'+SOURCE='+str(directory/'source.hex'),'+EXPECTED='+str(directory/'expected.hex'),
                    '+SAIF='+str(directory/'task.saif')],directory,'NEW_6BB1BEA_COLD_TASK_GOLDEN_PASS')
            metrics=dict(line.split('\t',1) for line in (directory/'TaskMetrics.tsv').read_text().splitlines())
            seconds=float(metrics['duration_ns'])*1e-9
            cycles=int(metrics['cycles'])
            # A half-period rounded to the simulator's 1fs grid can differ
            # from the DC period by 1fs. Retain actual SAIF time, within 1ppm.
            if int(metrics['effective_data_x_count'])!=0 or cycles<=0 or abs(seconds-cycles*6.666667e-9)>max(1e-11,seconds*1e-6):raise ValueError('Invalid activity window/X evidence')
            coverage=check_saif(directory/'task.saif',seconds)
            save(directory/'Activity.json',{'source_commit':REV,'system_netlist_sha256':current['netlist_sha256'],
                'saif_sha256':sha(directory/'task.saif'),'metrics':metrics,'duration_seconds':seconds,'native_saif':coverage})
        activity=load(directory/'Activity.json')
        if activity['system_netlist_sha256']!=current['netlist_sha256'] or sha(directory/'task.saif')!=activity['saif_sha256']:raise ValueError('Activity/netlist changed')
        power=directory/'power';power.mkdir(exist_ok=True)
        write_config(power,pdk,{'SystemDdc':system/'candidate.ddc','ActivityFile':directory/'task.saif'})
        if not (power/'Complete.json').is_file():
            native([DC,'-f',str(tools/'Power.tcl')],power,'NEW_6BB1BEA_POWER_REPORTS_COMPLETE')
            total=power_values((power/'power.rpt').read_text());groups={}
            for line in (power/'groups.tsv').read_text().splitlines():
                key,count=line.split('\t');count=int(count)
                if count:groups[key]=group_values((power/(key+'_power.rpt')).read_text(),count)
            difference=sum(g['total_w'] for g in groups.values())-total['total_w']
            if abs(difference)>max(1e-9,total['total_w']*.02):raise ValueError('Power group sum does not cover system total')
            seconds=activity['duration_seconds']
            data={'task':task,'source_commit':REV,'system_power':total,'groups':groups,
                'duration_seconds':seconds,'system_task_energy_j':total['total_w']*seconds,
                'group_sum_minus_system_total_w':difference,
                'system_timing_pass':current['timing_pass'],'activity':activity,
                'status':'TT_PRELAYOUT_ZERO_DELAY_COLD_TASK_ESTIMATE_COVERAGE_REVIEW_PENDING'}
            save(power/'Complete.json',data)
        result=load(power/'Complete.json');summaries.append(result)
        print('TASK_POWER: '+task+' system_mW='+str(result['system_power']['total_w']*1000)+' accelerator_mW='+str(result['groups']['ACCELERATOR']['total_w']*1000),flush=True)
        print('TASK_ENERGY: '+task+' system_uJ='+str(result['system_task_energy_j']*1e6),flush=True)
    verify(root,manifest)
    save(root/'PowerSummary.json',{'source_commit':REV,'tasks':summaries,'system':current,
        'scope':'CPU, original bus/new arbiter, current frozen accelerator/private SRAM, 512KiB shared SRAM, 64KiB ITCM and 64KiB DTCM; external QSPI source energy excluded',
        'status':'COLD_REPRESENTATIVE_TASK_REPORTS_COMPLETE_REVIEW_DEFAULT_PROPAGATED_X_COVERAGE_NOT_SIGNOFF'})
    print('NEW_6BB1BEA_COLD_TASK_POWER_REPORTS_COMPLETE_REVIEW_COVERAGE',flush=True)
    print('POWER_SUMMARY='+str(root/'PowerSummary.json'),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:print('NEW_POWER_STOPPED:',e,file=sys.stderr);sys.exit(2)
