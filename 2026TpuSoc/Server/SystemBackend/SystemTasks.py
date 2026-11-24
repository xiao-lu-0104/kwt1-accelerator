"""Prepare full CPU RTL + frozen accelerator + physical SRAM functional tasks/SAIF."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
from Prepare import check,sha

TASKS={'ff1':(1,25344,332348,45952,50688,45960),'encoder':(0,6336,1485712,112256,12672,112264)}
NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def saif_time(text):
    durations=re.findall(r'\(DURATION\s+('+NUMBER+r')\s*\)',text,re.I)
    scales=re.findall(r'\(TIMESCALE\s+('+NUMBER+r')\s+(fs|ps|ns|us|ms|s)\s*\)',text,re.I)
    if len(durations)!=1 or len(scales)!=1: raise ValueError('Missing/duplicate SAIF duration/unit; inspect saved header')
    raw=Decimal(durations[0]); scale=Decimal(scales[0][0])
    if not raw.is_finite() or not scale.is_finite() or raw<=0 or scale<=0: raise ValueError('Invalid SAIF duration/scale')
    unit=scales[0][1].lower()
    seconds=raw*scale*{'fs':Decimal('1e-15'),'ps':Decimal('1e-12'),'ns':Decimal('1e-9'),
        'us':Decimal('1e-6'),'ms':Decimal('1e-3'),'s':Decimal('1')}[unit]
    return {'raw_duration':str(raw),'scale_value':str(scale),'scale_unit':unit,'seconds':float(seconds)}


def verify_review_manifest(review):
    closed_journals=[]
    for line in (review/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1); path=(review/name).resolve()
        if review not in path.parents: raise ValueError('Unsafe review manifest path')
        if sha(path)==digest: continue
        # The old recovery manifest included its own still-open stdout journal.
        # Verify its original prefix exactly, then record the closed full journal.
        if not re.fullmatch(r'summary_recovery_v1_[A-Za-z0-9]+\.log',name):
            raise ValueError('Clock report/archive input changed: '+name)
        content=path.read_bytes(); boundary=content.find(b'CLOCK_PORT_REVIEW: NETLIST ')
        if boundary<0 or hashlib.sha256(content[:boundary]).hexdigest()!=digest:
            raise ValueError('Recovery runtime journal prefix changed: '+name)
        if not content.endswith(b'RECOVERY_RAW_REPORTS_UNCHANGED: PASS\n'):
            raise ValueError('Incomplete runtime recovery journal')
        closed_journals.append({'path':str(path),'verified_original_prefix_sha256':digest,'closed_full_sha256':sha(path)})
    return closed_journals


def physical_bench(text):
    for required in ('UNKNOWN_LOADER_COMMAND_READY','UNKNOWN_LOADER_RESPONSE_VALID','UNKNOWN_LOADER_READ_DATA',
                     'Result !== ExpectedHost[WordIndex]','TaskActivity.StartWindow();','TaskActivity.EndRequested = 1;'):
        if required not in text: raise ValueError('Passed strict task bench evidence missing: '+required)
    old='''        for (int Index = 0; Index < 65536; Index++) `DTCM[Index] = 0;
        $readmemh(Firmware, `ITCM);'''
    if text.count(old)!=1: raise ValueError('Unexpected original initialization')
    text=text.replace(old,'''        wait (TcmInitializer.Done && TcmInitializer.Released);
        if (ResetN !== 1'b0) $fatal(1,"CPU_RESET_DURING_PHYSICAL_INIT");''')
    text=re.sub(r'(?m)^\s*`define (?:I|D)TCM .*\n','',text)
    old='''$fatal(1, "CPU failed/trapped: done=%0d PC=%h error=%h cause=%h mepc=%h",
                Done, Pc, `DTCM[3], `DTCM[8], `DTCM[9]);'''
    if text.count(old)!=1: raise ValueError('Unexpected trap diagnostics')
    text=text.replace(old,'$fatal(1, "CPU failed/trapped: done=%0d PC=%h; physical TCM", Done, Pc);')
    if '`DTCM' in text or '`ITCM' in text or 'u_sirv_sim_ram.mem_r' in text: raise ValueError('Behavioral memory backdoor retained')
    text=text.replace('functional SRAM models; full platform and STA separate',
        'physical SRAM functional models; original CPU RTL and frozen mapped accelerator; no full-system gate/SDF claim')
    return text


def shared_guard():
    lines=['`timescale 1ns/1ps','module SharedTcmGuard;',
        'longint unsigned Reads[0:63],Writes[0:63]; bit Complete=0;',
        'initial for (int I=0;I<64;I++) begin Reads[I]=0; Writes[I]=0; end']
    index=0
    for kind,banks,lanes in (('itcm',8,4),('dtcm',16,2)):
        for bank in range(banks):
            for lane in range(lanes):
                p=f'SharedTest.Cpu.u_e203_srams.u_e203_{kind}_ram.u_e203_{kind}_gnrl_ram.Banks[{bank}].Lanes[{lane}].Macro'
                lines += ['always @(posedge SharedTest.Clock) if (TaskActivity.Started && !TaskActivity.Stopped) begin',
                    f'if ($isunknown({p}.CEN)) $fatal(1,"SHARED_MACRO_CEN_X {index}");',
                    f'if ({p}.CEN===1\'b0) begin',
                    f'if ($isunknown({{{p}.A,{p}.GWEN,{p}.WEN,{p}.RET1N}})) $fatal(1,"SHARED_MACRO_CONTROL_X {index}");',
                    f'if ({p}.GWEN===1\'b0) begin Writes[{index}]++;',
                    f'for (int B=0;B<16;B++) if (!{p}.WEN[B] && $isunknown({p}.D[B])) $fatal(1,"SHARED_MACRO_WRITE_X {index}");',
                    f'end else begin Reads[{index}]++; #0.001;',
                    f'if ($isunknown({p}.Q)) $fatal(1,"SHARED_MACRO_READ_Q_X {index}");',
                    'end end end']
                index+=1
    lines += ['initial begin longint unsigned R,W; wait(TaskActivity.Stopped); #0.003; R=0; W=0;',
        'for (int I=0;I<64;I++) begin R+=Reads[I]; W+=Writes[I]; end',
        'if (R==0 || W==0) $fatal(1,"SHARED_MACROS_NOT_EXERCISED");',
        'if (!TcmInitializer.Done || !TcmInitializer.Released) $fatal(1,"INITIALIZER_ACTIVE_IN_TASK");',
        'Complete=1; $display("PASS SHARED_TCM_GUARD: reads=%0d writes=%0d; initialized physical macros; input and post-read Q known",R,W); end',
        'final $display("SHARED_TCM_GUARD_FINAL: complete=%b",Complete);','endmodule']
    return '\n'.join(lines)+'\n'


def prepare(out,tools,review):
    check(json.loads((review/'Inputs.json').read_text()))
    done=json.loads((review/'ClockPortSummary.json').read_text())
    if done['SETUP_STATUS']!='PASS' or done['HOLD_STATUS']!='PASS': raise ValueError('Current system timing view must pass')
    closed_journals=verify_review_manifest(review)
    base=Path(json.loads((review/'Inputs.json').read_text())['source'])
    record=json.loads((base/'SystemBaseRecoveryInputs.json').read_text()); check(record)
    source=Path(record['source']); qualification=Path(record['qualification'])
    power=json.loads((source/'TaskPowerInputs.json').read_text()); check(power)
    functional=Path((source/'Functional.txt').read_text().strip())
    firmware=functional/'project/Firmware.hex'
    words=firmware.read_text().split()
    if len(words)!=32768 or any(not re.fullmatch('[0-9a-fA-F]{16}',w) for w in words): raise ValueError('Expected full original 64-bit ITCM firmware image')
    bench=out/'PhysicalSharedTest.sv'; bench.write_text(physical_bench((source/'TaskSharedTest.sv').read_text()))
    candidate=out/'candidate.v'; shutil.copy2(base/'frozen_accelerator.v',candidate)
    if sha(candidate)!='b366417d57d6251f13a827933288886637b61071472d391b121a7341fa2ea75e': raise ValueError('Frozen accelerator changed')
    lines=(source/'Task.f').read_text().splitlines(); found_bench=found_candidate=found_ram=0
    result=[]
    for line in lines:
        if line==str(source/'TaskSharedTest.sv'): line=str(bench); found_bench+=1
        elif line==str(source/'candidate.v'): line=str(candidate); found_candidate+=1
        elif not line.startswith(('+','-')) and Path(line).name=='sirv_gnrl_ram.v':
            line=str(base/'tools/TcmMacro.sv'); found_ram+=1
        result.append(line)
    if (found_bench,found_candidate,found_ram)!=(1,1,1): raise ValueError('Unexpected original task file list')
    shared=Path((base/'SharedModel.txt').read_text().strip()); result.append('-v '+str(shared))
    (out/'Task.f').write_text('\n'.join(result)+'\n')
    for name in ('GateResetInventory.sv','IcbMirror.sv'): shutil.copy2(source/name,out/name)
    shutil.copy2(qualification/'EffectiveDataGuard.sv',out/'EffectiveDataGuard.sv')
    activity=(tools/'TaskActivity.sv').read_text()
    old='SharedTest.Cpu.u_e203_cpu.u_e203_nice_core'
    if activity.count(old)!=2: raise ValueError('Unexpected activity observer')
    activity=activity.replace(old,'SharedTest.Cpu')
    activity=activity.replace('if (Started || Stopped)',
        'if (!TcmInitializer.Done || !TcmInitializer.Released) $fatal(1,"SYSTEM_SAIF_STARTED_DURING_INIT");\n        if (Started || Stopped)')
    (out/'SystemActivity.sv').write_text(activity)
    (out/'SharedTcmGuard.sv').write_text(shared_guard())
    (out/'Bundle.txt').write_bytes((source/'Bundle.txt').read_bytes())
    (out/'Firmware.txt').write_text(str(firmware)+'\n')
    inputs=dict(record['inputs'])
    inputs.update(json.loads((review/'Inputs.json').read_text())['inputs'])
    for name in ('ClockPortSummary.json','clock_ports_corrected.sdc','MANIFEST.sha256'): inputs[str(review/name)]=sha(review/name)
    for item in closed_journals: inputs[item['path']]=item['closed_full_sha256']
    for p in (firmware,source/'TaskPowerInputs.json',base/'tools/TcmMacro.sv',shared): inputs[str(p)]=sha(p)
    for root in (out,tools):
        for p in root.iterdir():
            if p.is_file() and p.name not in ('runner.log','prepare.log'): inputs[str(p)]=sha(p)
    # Include all directly referenced HDL and library files in the new simulation list.
    for line in result:
        p=Path(line[3:]) if line.startswith('-v ') else Path(line) if line and not line.startswith(('+','-')) else None
        if p: inputs[str(p)]=sha(p)
    (out/'Inputs.json').write_text(json.dumps({'source':str(base),'review':str(review),'inputs':inputs,
        'closed_review_runtime_journals':closed_journals,
        'scope':'Original CPU RTL/controllers + frozen mapped accelerator + real functional SRAM macro models; system-scope task SAIF; no full-system gate/SDF claim',
        'initialization':'Original full firmware and DTCM zeros written/readback through physical RAM wrapper ports under reset; all init forces released before CPU startup; original pattern2 accelerator FF seed retained'},indent=2)+'\n')
    print('SYSTEM_TASK_PREPARED: original strict golden/ICB checks retained; physical TCM initialization before CPU startup; system SAIF scope SharedTest/Cpu',flush=True)


def validate(out,name):
    check(json.loads((out/'Inputs.json').read_text()))
    kind,values,baseline_cycles,reads,writes,loaded=TASKS[name]
    text=(out/name/'run.log').read_text(errors='replace')
    passes=re.findall(rf'^PASS SHARED: kind={kind} layers=1 values={values} cycles=(\d+) DMA_read_bytes={reads} DMA_write_bytes={writes} loaded_bytes={loaded}$',text,re.M)
    if len(passes)!=1 or int(passes[0])<=0: raise ValueError('Missing strict golden and DMA result: '+name)
    cycles=int(passes[0])
    required=['PASS PHYSICAL_TCM_INIT: ITCM_writes=32768 DTCM_writes=65536 ITCM_readback=32768 DTCM_readback=65536;',
        'PHYSICAL_TCM_INIT_FINAL: done=1 released=1',
        'INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0',
        'ICB_MIRROR_FINAL: divergence_observed=0','TASK_ACTIVITY_FINAL: started=1 stopped=1',
        'EFFECTIVE_GUARD_FINAL: complete=1','SHARED_TCM_GUARD_FINAL: complete=1']
    if any(r not in text for r in required) or re.search(r'Fatal:|FATAL:|Error-\[|NEW_CONTROL_QX:',text): raise ValueError('Full physical-TCM task checks failed: '+name)
    matches=re.findall(r'TASK_ACTIVITY_END: cycles=(\d+) duration_ns=([\d.]+)',text)
    if len(matches)!=1 or int(matches[0][0])!=cycles or abs(float(matches[0][1])-cycles*6.667)>0.002: raise ValueError('Task activity window changed')
    path=out/name/'task.saif'; saif=path.read_text()
    timing=saif_time(saif); seconds=timing['seconds']
    if abs(seconds-cycles*6.667e-9)>2e-12: raise ValueError('System SAIF duration mismatch')
    if not re.search(r'\(INSTANCE\s+u_e203_srams\b',saif) or not re.search(r'\(INSTANCE\s+u_e203_cpu\b',saif): raise ValueError('System SAIF scope incomplete')
    if not re.search(r'\(TC\s+[1-9]\d*\s*\)',saif): raise ValueError('No nonzero system switching')
    tx=[float(v) for v in re.findall(r'\(TX\s+('+NUMBER+r')\s*\)',saif)]
    tz=[float(v) for v in re.findall(r'\(TZ\s+('+NUMBER+r')\s*\)',saif)]
    result={'task':name,'status':'PASS_PHYSICAL_TCM_TASK_AND_SYSTEM_ACTIVITY','cycles':cycles,
        'previous_behavioral_tcm_cycles':baseline_cycles,'cycles_match_previous_behavioral_tcm':cycles==baseline_cycles,'duration_seconds':seconds,
        'saif_sha256':sha(path),'saif_bytes':path.stat().st_size,
        'TX_entries':len(tx),'TX_nonzero_entries':sum(v>0 for v in tx),'TZ_nonzero_entries':sum(v>0 for v in tz),
        'max_individual_TX_fraction':max(tx,default=0)/float(timing['raw_duration']),
        'saif_time_header':timing,
        'power':'PENDING_SYSTEM_DDC_ANNOTATION_AND_X_REVIEW',
        'simulation':'Original CPU RTL + frozen gate accelerator + real functional SRAM macros; zero delay; explicit released accelerator reset seed'}
    (out/name/'Activity.json').write_text(json.dumps(result,indent=2)+'\n')
    print('SYSTEM_TASK_ACTIVITY:',json.dumps(result,sort_keys=True),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('prepare','validate'))
    p.add_argument('out',type=Path); p.add_argument('--review',type=Path); p.add_argument('--task',choices=TASKS)
    a=p.parse_args()
    if a.mode=='prepare': prepare(a.out.resolve(),Path(__file__).resolve().parent,a.review.resolve())
    else: validate(a.out.resolve(),a.task)
