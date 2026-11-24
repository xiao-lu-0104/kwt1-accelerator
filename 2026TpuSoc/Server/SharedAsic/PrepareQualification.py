"""Prepare passive effective-data checks on the exact previously measured gate design."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from ReadProbe import instances

PREFIX=('SharedTest','Cpu','u_e203_cpu','u_e203_nice_core')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def check(record):
    for filename,digest in record['inputs'].items():
        if sha(Path(filename))!=digest: raise ValueError('Frozen input changed: '+filename)


def svpath(parts):
    return '.'.join(p if re.fullmatch(r'[A-Za-z_]\w*',p) else '\\'+p+' ' for p in parts)


def guard(candidate):
    # Index each module and parse its instances once. Never search the complete
    # netlist for every standard-cell instance: that scales quadratically.
    designs={}
    for match in re.finditer(r'(?m)^[ \t]*module[ \t]+([A-Za-z_]\w*)\b.*?\bendmodule\b',candidate,re.S):
        if match[1] in designs: raise ValueError('Duplicate candidate module: '+match[1])
        designs[match[1]]=match[0]
    if 'e203_subsys_nice_core' not in designs: raise ValueError('Candidate top module missing')
    children={ref:tuple(instances(body)) for ref,body in designs.items()}
    paths={}; macros=[]
    def visit(ref,path,chain=()):
        if ref in chain: raise ValueError('Recursive mapped hierarchy: '+ref)
        paths[path]=designs[ref]
        for cell,name,ports in children[ref]:
            child=path+(name.lstrip('\\').strip(),)
            if cell in designs:
                visit(cell,child,chain+(ref,))
            elif cell=='RAMSP1024X16':
                macros.append(child)
    visit('e203_subsys_nice_core',PREFIX)
    def wire(path,name):
        if path not in paths or not re.search(r'\b'+re.escape(name)+r'\b',paths[path]):
            raise ValueError('Required observed signal missing: '+svpath(path)+'.'+name)
        return svpath(path)+'.'+name
    dma=PREFIX+('Tpu','Core','Dma')
    dot=PREFIX+('Tpu','Core','Matrix','Dot')
    bias=PREFIX+('Tpu','Core','Matrix','BiasBuffer')
    reset=wire(PREFIX,'nice_rst_n')
    specs=[('DOT_OPERANDS',wire(dot,'InputValid'),'{'+wire(dot,'InputOperandA')+','+wire(dot,'InputOperandB')+'}'),
           ('BIAS_WRITE',wire(bias,'WriteValid'),wire(bias,'WriteData')),
           ('DMA_OUTPUT',wire(dma,'WriteDataValid'),wire(dma,'WriteData')),
           ('DMA_INPUT',wire(dma,'ReadDataValid')+' && '+wire(dma,'ReadDataReady'),
            '{'+','.join(wire(dma,n) for n in ('ReadData','ReadDataLast','ReadDataError'))+'}'),
           ('DMA_SRAM_CAPTURE','DmaReadTags[2]',wire(dma,'SramReadData'))]
    text=['`timescale 1ns/1ps','module EffectiveDataGuard;',
          'longint unsigned Valid[0:4], IdleX[0:4];',
          'longint unsigned MacroReads=0, MacroReadQX=0, MacroWrites=0;',
          'logic [2:0] DmaReadTags=0; bit Complete=0;',
          'initial for (int I=0;I<5;I++) begin Valid[I]=0; IdleX[I]=0; end',
          'always @(posedge SharedTest.Clock) begin',
          f'if (!{reset}) DmaReadTags<=0;',
          f'else DmaReadTags<={{DmaReadTags[1:0],{wire(dma,"SramReadValid")} && {wire(dma,"SramReadReady")}}};',
          'if (TaskActivity.Started && !TaskActivity.Stopped) begin',
          f'if ({reset}!==1\'b1) $fatal(1,"EFFECTIVE_TASK_RESET_INVALID");']
    for index,(label,enable,data) in enumerate(specs):
        text += [f'if ($isunknown({enable})) $fatal(1,"EFFECTIVE_CONTROL_X {label}");',
                 f'if ({enable}) begin Valid[{index}]++;',
                 f'if ($isunknown({data})) $fatal(1,"EFFECTIVE_DATA_X {label} cycle=%0d",SharedTest.Cycles);',
                 f'end else if ($isunknown({data})) IdleX[{index}]++;']
    if len(macros)!=56: raise ValueError('Expected 56 original SRAM macros')
    for index,path in enumerate(macros):
        p=svpath(path)
        text += [f'if ($isunknown({p}.CEN)) $fatal(1,"MACRO_ENABLE_X {index}");',
                 f'if ({p}.CEN===1\'b0) begin',
                 f'if ($isunknown({{{p}.GWEN,{p}.WEN,{p}.A,{p}.RET1N}})) $fatal(1,"MACRO_ACTIVE_CONTROL_X {index}");',
                 f'if ({p}.GWEN===1\'b0) begin MacroWrites++;',
                 f'for (int B=0;B<16;B++) if (!{p}.WEN[B] && $isunknown({p}.D[B])) $fatal(1,"MACRO_WRITTEN_BIT_X {index}");',
                 'end else begin MacroReads++;',
                 # Input-edge Q describes the previous output, not a read-latency verdict.
                 f'if ($isunknown({p}.Q)) MacroReadQX++; end end']
    text += ['end end','initial begin wait(TaskActivity.Stopped); #0.002;',
             'for (int I=0;I<5;I++) if (Valid[I]==0) $fatal(1,"UNEXERCISED_EFFECTIVE_GUARD %0d",I);',
             'if (MacroReads==0 || MacroWrites==0) $fatal(1,"UNEXERCISED_MACRO_GUARD");']
    for index,(label,_,__) in enumerate(specs):
        text += [f'$display("EFFECTIVE_DATA_SUMMARY: {label} valid=%0d idle_X_cycles=%0d",Valid[{index}],IdleX[{index}]);']
    text += ['$display("MACRO_INPUT_SUMMARY: reads=%0d writes=%0d previous_Q_X_on_read_edge=%0d; no Q-X waiver",MacroReads,MacroWrites,MacroReadQX);',
             'Complete=1; $display("PASS EFFECTIVE_DATA_GUARD: original task window; no observed X at qualified consumers or active SRAM input bits"); end',
             'final $display("EFFECTIVE_GUARD_FINAL: complete=%b",Complete);','endmodule']
    return '\n'.join(text)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    args=parser.parse_args(); out=args.out.resolve()
    started=time.monotonic()
    print('PREP_STAGE: locating completed object audit',flush=True)
    choices=sorted((Path.home()/'soc').glob('tpusoc_activity_objects_20261106_*'),key=lambda p:p.stat().st_mtime,reverse=True)
    audit=next((p for p in choices if (p/'ObjectAuditSummary.json').exists() and
        'RESULT: ACTIVITY_OBJECT_AUDIT_COMPLETE' in (p/'runner.log').read_text()),None)
    if audit is None: raise ValueError('Completed object audit required')
    record=json.loads((audit/'ObjectAuditInputs.json').read_text())
    print('PREP_STAGE: checking frozen audit inputs; files='+str(len(record['inputs'])),flush=True)
    check(record)
    source=Path(record['source'])
    power=json.loads((source/'TaskPowerInputs.json').read_text())
    print('PREP_STAGE: checking original task inputs; files='+str(len(power['inputs'])),flush=True)
    check(power)
    inputs=dict(record['inputs'])
    candidate=source/'candidate.v'
    if sha(candidate)!='b366417d57d6251f13a827933288886637b61071472d391b121a7341fa2ea75e':
        raise ValueError('Original candidate changed')
    print('PREP_STAGE: indexing mapped modules once and generating passive guard; bytes='+str(candidate.stat().st_size),flush=True)
    (out/'EffectiveDataGuard.sv').write_text(guard(candidate.read_text()))
    print('PREP_STAGE: passive guard generated; elapsed_seconds='+format(time.monotonic()-started,'.3f'),flush=True)
    # All task stimulus, assertions, pattern2 reset/release and golden checks are reused.
    (out/'Task.f').write_text((source/'Task.f').read_text())
    evidence=json.loads((audit/'SharedSramMacroEvidence.json').read_text())
    raw=Path(evidence['model'])
    if sha(raw)!=evidence['model_sha256']: raise ValueError('Shared macro model changed')
    (out/'Macro.txt').write_text(str(raw)+'\n')
    (out/'Source.txt').write_text(str(source)+'\n')
    for name in ('Ddc.txt','StdDb.txt','SpDb.txt'):
        (out/name).write_bytes((source/name).read_bytes())
    for path in (audit/'ObjectAuditSummary.json',audit/'SharedSramMacroEvidence.json',
                 source/'TaskPowerInputs.json',source/'Task.f',candidate,raw): inputs[str(path)]=sha(path)
    for path in Path(__file__).parent.iterdir():
        if path.is_file(): inputs[str(path)]=sha(path)
    for path in out.iterdir():
        if path.is_file() and path.name!='runner.log': inputs[str(path)]=sha(path)
    (out/'QualificationInputs.json').write_text(json.dumps({'source':str(source),'audit':str(audit),
        'inputs':inputs,'power_acceptance':'PENDING; effective-use checks do not bound unknown switching power'},indent=2)+'\n')
    print('VERIFIED_QUALIFICATION_SOURCE:',source)
    print('QUALIFICATION_SCOPE: original mapped accelerator, qualified consumer inputs; isolated shared macro; no synthesis/activity override')
    print('PREP_COMPLETE: elapsed_seconds='+format(time.monotonic()-started,'.3f'),flush=True)


if __name__=='__main__': main()
