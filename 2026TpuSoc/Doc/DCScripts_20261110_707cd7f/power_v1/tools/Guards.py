"""Passive current eight-row-pipeline checks; no DUT drive or X masking."""
import re
from ReadProbe import instances

PREFIX=('SharedTest','Cpu','u_e203_cpu','u_e203_nice_core')


def svpath(parts):
    return '.'.join(p if re.fullmatch(r'[A-Za-z_]\w*',p) else '\\'+p+' ' for p in parts)


def effective_guard(text):
    modules={m[1]:m[0] for m in re.finditer(r'(?m)^[ \t]*module[ \t]+([A-Za-z_]\w*)\b.*?\bendmodule\b',text,re.S)}
    children={ref:tuple(instances(body)) for ref,body in modules.items()}
    paths={}; macros=[]
    def walk(ref,path,chain=()):
        if ref in chain: raise ValueError('Recursive gate hierarchy')
        paths[path]=modules[ref]
        for cell,name,ports in children[ref]:
            child=path+(name.lstrip('\\').strip(),)
            if cell in modules: walk(cell,child,chain+(ref,))
            elif cell=='RAMSP1024X16': macros.append(child)
    walk('e203_subsys_nice_core',PREFIX)
    def wire(path,name):
        if path not in paths or not re.search(r'\b'+re.escape(name)+r'\b',paths[path]):
            raise ValueError('Missing current guard signal '+svpath(path)+'.'+name)
        return svpath(path)+'.'+name
    dots=[p for p in paths if p[-1].endswith('Dot') and all(re.search(r'\b'+n+r'\b',paths[p]) for n in ('InputValid','InputOperandA','InputOperandB'))]
    if len(dots)!=8 or len(macros)!=56: raise ValueError('Expected eight dot pipelines and 56 private macros')
    specs=[]
    for i,p in enumerate(sorted(dots)):
        specs.append(('DOT_'+str(i),wire(p,'InputValid'),'{'+wire(p,'InputOperandA')+','+wire(p,'InputOperandB')+'}'))
    dma=PREFIX+('Tpu','Core','Dma'); bias=PREFIX+('Tpu','Core','Matrix','BiasBuffer')
    specs += [('BIAS_WRITE',wire(bias,'WriteValid'),wire(bias,'WriteData')),
        ('DMA_OUTPUT',wire(dma,'WriteDataValid'),wire(dma,'WriteData')),
        ('DMA_INPUT',wire(dma,'ReadDataValid')+' && '+wire(dma,'ReadDataReady'),'{'+','.join(wire(dma,n) for n in ('ReadData','ReadDataLast','ReadDataError'))+'}'),
        ('DMA_SRAM_CAPTURE','DmaReadTags[2]',wire(dma,'SramReadData'))]
    reset=wire(PREFIX,'nice_rst_n'); count=len(specs)
    lines=['`timescale 1ns/1ps','module EffectiveDataGuard;',
        'longint unsigned Valid[0:%d], IdleX[0:%d];'%(count-1,count-1),
        'longint unsigned MacroReads=0,MacroWrites=0,PreviousQX=0; logic [2:0] DmaReadTags=0; bit Complete=0;',
        'initial for(int I=0;I<%d;I++) begin Valid[I]=0; IdleX[I]=0; end'%count,
        'always @(posedge SharedTest.Clock) begin',
        'if (!%s) DmaReadTags<=0; else DmaReadTags<={DmaReadTags[1:0],%s && %s};'%(reset,wire(dma,'SramReadValid'),wire(dma,'SramReadReady')),
        'if(TaskActivity.Started && !TaskActivity.Stopped) begin',
        'if(%s!==1\'b1) $fatal(1,"EFFECTIVE_TASK_RESET_INVALID");'%reset]
    for i,(label,enable,data) in enumerate(specs):
        lines += ['if($isunknown(%s)) $fatal(1,"EFFECTIVE_CONTROL_X %s");'%(enable,label),
            'if(%s) begin Valid[%d]++; if($isunknown(%s)) $fatal(1,"EFFECTIVE_DATA_X %s cycle=%%0d",SharedTest.Cycles); end'%(enable,i,data,label),
            'else if($isunknown(%s)) IdleX[%d]++;'%(data,i)]
    for i,path in enumerate(macros):
        p=svpath(path)
        lines += ['if($isunknown(%s.CEN)) $fatal(1,"MACRO_ENABLE_X %d");'%(p,i),
            'if(%s.CEN===1\'b0) begin if($isunknown({%s.GWEN,%s.WEN,%s.A,%s.RET1N})) $fatal(1,"MACRO_ACTIVE_CONTROL_X %d");'%(p,p,p,p,p,i),
            'if(%s.GWEN===1\'b0) begin MacroWrites++; for(int B=0;B<16;B++) if(!%s.WEN[B] && $isunknown(%s.D[B])) $fatal(1,"MACRO_WRITTEN_BIT_X %d"); end'%(p,p,p,i),
            'else begin MacroReads++; if($isunknown(%s.Q)) PreviousQX++; end end'%p]
    lines += ['end end','initial begin wait(TaskActivity.Stopped); #0.002;',
        'for(int I=0;I<%d;I++) if(Valid[I]==0) $fatal(1,"UNEXERCISED_EFFECTIVE_GUARD %%0d",I);'%count,
        'if(MacroReads==0 || MacroWrites==0) $fatal(1,"UNEXERCISED_PRIVATE_MACROS");']
    for i,(label,_,_) in enumerate(specs):
        lines.append('$display("EFFECTIVE_DATA_SUMMARY: %s valid=%%0d idle_X_cycles=%%0d",Valid[%d],IdleX[%d]);'%(label,i,i))
    lines += ['$display("MACRO_INPUT_SUMMARY: reads=%0d writes=%0d previous_Q_X=%0d; no Q-X waiver",MacroReads,MacroWrites,PreviousQX);',
        'Complete=1; $display("PASS EFFECTIVE_DATA_GUARD: eight dot pipelines and qualified consumers checked"); end',
        'final $display("EFFECTIVE_GUARD_FINAL: complete=%b",Complete);','endmodule']
    return '\n'.join(lines)+'\n'
