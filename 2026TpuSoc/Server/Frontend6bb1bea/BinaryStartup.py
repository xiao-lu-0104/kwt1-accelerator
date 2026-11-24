"""Explicit binary power-up of mapped accelerator FFs during one reset clock."""
import hashlib
import json
from pathlib import Path
import re


def generate(root, directory, cells):
    from RunPower import sv_path
    models={}
    for p in sorted((root/'models').glob('*')):
        if p.is_file():
            for m in re.finditer(r'\bmodule\s+(\w+)\b.*?\bendmodule\b',p.read_text(errors='replace'),re.S):
                models[m.group(1)]=m.group(0)
    rows=[]
    for name,ref in sorted(cells.items()):
        if not name.startswith('Backend/Accelerator/'):continue
        body=models.get(ref,'')
        clean=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S)
        sequential=bool(re.search(r'\budp_\w*(?:dff|latch)\w*\b',clean,re.I))
        if re.match(r'(?:S?DQ|S?DFF)',ref) and not sequential:
            raise ValueError('Unclassified sequential model '+ref)
        if not sequential:continue
        if re.search('latch',clean,re.I):raise ValueError('Latch initialization needs separate review: '+ref)
        outs=[]
        for m in re.finditer(r'\boutput\s+([^;]+);',clean):
            outs += re.sub(r'\[[^\]]*\]|\b(?:wire|reg|logic)\b','',m.group(1)).replace(' ','').split(',')
        outs=[q for q in ('Q','QN') if q in outs]
        if not outs or not re.search(r'\bD\b',clean):raise ValueError('Unrecognized FF '+ref)
        rows.append({'scope':'PowerTest.Dut.'+sv_path(name),'ref':ref,'outputs':outs,
                     'seed':hashlib.sha256(name.encode()).digest()[0]&1})
    if not 100 < len(rows) < 100000:raise ValueError('Unexpected accelerator FF count '+str(len(rows)))
    count=len(rows)
    bits=''.join(str(row['seed']) for row in reversed(rows))
    forces=[];releases=[];checks=[]
    for i,row in enumerate(rows):
        for pin in row['outputs']:
            target=row['scope']+'.'+pin
            rhs=('~' if pin=='QN' and 'Q' in row['outputs'] else '')+'Values[%d]'%i
            forces.append('force '+target+'='+rhs+';')
            releases.append('release '+target+';')
        if '.Bus.' in row['scope'] and re.search(r'CopyDestination|State|Remaining|WordIndex|Address|Outstanding',row['scope']):
            target=row['scope']+'.'+row['outputs'][0]
            checks.append('if($isunknown('+target+')) $fatal(1,'+json.dumps('STARTUP_CONTROL_X '+row['scope'])+');')
    if not checks:raise ValueError('No Bus startup controls identified')
    code=['`timescale 1ns/1fs','module MappedBinaryStartup;',
          'integer Pattern=2;bit Released=0,Checked=0;','logic [%d:0] Values;'%(count-1),
          'initial begin',
          'if($value$plusargs("INIT_PATTERN=%d",Pattern)) begin end',
          'if(Pattern<0 || Pattern>2) $fatal(1,"Bad startup pattern");',
          "Values=Pattern==0 ? '0 : Pattern==1 ? '1 : %d'b%s;"%(count,bits),
          '#0.001;if(PowerTest.ResetN!==0) $fatal(1,"Startup requires asserted reset");']+forces+[
          '@(posedge PowerTest.Clock);@(negedge PowerTest.Clock);#0.001;']+releases+[
          'Released=1;repeat(3) @(negedge PowerTest.Clock);#0.001;',
          'if(PowerTest.ResetN!==0) $fatal(1,"Insufficient reset interval");']+checks+[
          'Checked=1;',
          '$display("BINARY_STARTUP_RELEASED_PASS FF=%d pattern=%%0d; all forces released after first reset clock",Pattern);'%count,
          'end',
          'always @(posedge PowerTest.ResetN) if(!Released || !Checked) $fatal(1,"Startup not released/checked");',
          'initial if($test$plusargs("STARTUP_CHECK_ONLY")) begin',
          "wait(PowerTest.ResetN===1'b1);repeat(520) @(negedge PowerTest.Clock);",
          '$display("BINARY_STARTUP_SHORT_PASS pattern=%0d",Pattern);$finish;end',
          'final $display("BINARY_STARTUP_FINAL pattern=%0d released=%b checked=%b",Pattern,Released,Checked);',
          'endmodule']
    p=directory/'MemoryInit.sv'
    original=p.read_text()
    assert original.count('module MemoryInit;')==1
    p.write_text(original.replace('module MemoryInit;','module MemoryInit;\nMappedBinaryStartup Startup();',1)+'\n'+'\n'.join(code)+'\n')
    (directory/'BinaryStartup.json').write_text(json.dumps({'policy':'mapped accelerator FF binary initial state only; released after first reset clock; no CPU/SRAM/task input forcing',
        'default_pattern':2,'register_count':count,'registers':rows},indent=2)+'\n')
    print('BINARY_STARTUP_GENERATED FF='+str(count),flush=True)
