#!/usr/bin/env bash
set -euo pipefail
task_probe_log="/tmp/copy_register_6bb1bea_$(id -u)_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$task_probe_log") 2>&1
echo "DIAGNOSTIC_LOG=$task_probe_log"
python3 - <<'PY'
from pathlib import Path
import ast,hashlib,json,os,re,subprocess,sys,time
root=Path('/tmp/final_power_6bb1bea_'+str(os.getuid()))
system=root/'system'
raw=(system/'candidate.v').read_bytes()
expected=json.loads((system/'Complete.json').read_text())['netlist_sha256']
assert hashlib.sha256(raw).hexdigest()==expected,'System candidate changed'
text=raw.decode()
modules={m.group(1):m.group(0) for m in re.finditer(r'\bmodule\s+(\w+)\b.*?\bendmodule\b',text,re.S)}
acc=modules['SubmissionAccelerator']
m=re.search(r'\b(\w+)\s+Bus\s*\(',acc)
assert m,'Mapped Bus instance missing'
bus=modules[m.group(1)]
print('BUS_REFERENCE='+m.group(1),flush=True)
for line in bus.splitlines():
    if re.search(r'\b(?:wire|input|output)\b',line) and ('CopyDestination' in line or 'ResetN' in line): print('DECL '+line.strip(),flush=True)
instances=[]
for cell in re.finditer(r'\b(\w+)\s+(\\[^\s]+\s|[\w$]+)\s*\((.*?)\)\s*;',bus,re.S):
    pins=dict(re.findall(r'\.(\w+)\s*\(([^()]*)\)',cell.group(3),re.S))
    if pins:instances.append((cell.group(1),cell.group(2).strip(),{p:re.sub(r'\s+','',v) for p,v in pins.items()},cell.group(0)))
selected=[c for c in instances if any('CopyDestination' in v for v in c[2].values())]
probe_listing=root/('copy_destination_cells_'+time.strftime('%Y%m%d_%H%M%S')+'.txt')
probe_listing.write_text('\n'.join(c[3] for c in selected))
print('DESTINATION_CELL_LIST='+str(probe_listing),flush=True)
# Print driver cones of high destination bits, including optimized internal nets.
outputs={'Q','QN','Z','ZN','Y','O','CO','S'}
drivers={v:c for c in instances for p,v in c[2].items() if p in outputs and re.fullmatch(r'[\w$]+(?:\[\d+\])?',v)}
seeds=['CopyDestination[%d]'%b for b in range(27,32)]
seen=set();front=seeds[:]
for depth in range(4):
    more=[]
    for net in front:
        if net in seen:continue
        seen.add(net);c=drivers.get(net)
        if not c:continue
        print('HIGH_CONE depth=%d net=%s %s'%(depth,net,re.sub(r'\s+',' ',c[3])),flush=True)
        more += [v for p,v in c[2].items() if p not in outputs]
    front=more
probe=root/('copy_register_probe_'+time.strftime('%Y%m%d_%H%M%S'));probe.mkdir()
scope='PowerTest.Dut.Backend.Accelerator.Bus'
signals={'rst':scope+'.ResetN','clk':scope+'.Clock','valid':scope+'.CopyRequestValid','ready':scope+'.CopyRequestReady','dest_in':scope+'.CopyDestinationAddress','saved':scope+'.CopyDestination','dma_addr':'PowerTest.Dut.Backend.DmaRequestAddress','dma_valid':'PowerTest.Dut.Backend.DmaRequestValid'}
if re.search(r'\bState\s*;',bus):signals['state']=scope+'.State'
# Sample true cell pins in the upper-bit cone, using the actual mapped names.
focus=[c for c in instances if any(v in seen for p,v in c[2].items() if p in outputs)]
focus=[c for c in focus if re.search(r'DFF|SDFF|DFF|LATCH|LAT',c[0],re.I)]
for idx,(ref,name,pins,source) in enumerate(focus[:8]):
    escaped=name if re.fullmatch(r'[A-Za-z_]\w*',name) else '\\'+name+' '
    for pin in pins:
        if pin.upper() in {'D','Q','QN','CK','CLK','CP','RN','SN','RESETN','CDN','SDN'}:
            signals['c%d_%s'%(idx,pin)]=scope+'.'+escaped+'.'+pin
    print('PIN_CELL c%d %s %s'%(idx,ref,name),flush=True)
formats=' '.join(k+'=%h' for k in signals)
args=','.join(signals.values())
sv='''`timescale 1ns/1fs
module CopyRegisterProbe;
integer N=0, Window=0;
initial begin
repeat(10) begin @(negedge PowerTest.Clock); $display("RESET_PIN_TRACE N=%0d FORMAT",N,ARGS);N=N+1;end
wait(PowerTest.ResetN===1'b1);
for(N=0;N<900;N=N+1) begin
 @(negedge PowerTest.Clock);
 if(SCOPE.CopyRequestValid===1'b1) Window=14;
 if(N<4 || Window>0) begin
   $display("COPY_PIN_TRACE N=%0d FORMAT",N,ARGS);
   if(Window>0) Window=Window-1;
 end
end
$display("COPY_REGISTER_PROBE_COMPLETE");$finish;
end
endmodule
'''.replace('FORMAT',formats).replace('ARGS',args).replace('SCOPE',scope)
(probe/'CopyRegisterProbe.sv').write_text(sv)
tree=ast.parse((root/'ff1/compile/Compile.py').read_text())
cmds=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cmd' for t in n.targets)]
assert len(cmds)==1
cmd=cmds[0];cmd[cmd.index('-o')+1]=str(probe/'simv')
cmd += [str(probe/'CopyRegisterProbe.sv'),'-top','CopyRegisterProbe']
build=probe/'compile';build.mkdir()
helper=build/'Compile.py'
helper.write_text('import subprocess\nsubprocess.check_call('+repr(cmd)+')\nprint("COPY_REGISTER_PROBE_COMPILED")\n')
sys.path.insert(0,str(root/'tools'))
from NativeHelpers import native
native(['python3',str(helper)],build,'COPY_REGISTER_PROBE_COMPILED')
run=probe/'run';run.mkdir()
r=subprocess.run([str(probe/'simv'),'+TASK=ff1','+SOURCE='+str(root/'ff1/source.hex'),'+EXPECTED='+str(root/'ff1/expected.hex'),'+SAIF='+str(run/'unused.saif')],cwd=str(run),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(run/'native.log').write_bytes(r.stdout)
for line in r.stdout.decode(errors='replace').splitlines():
    if any(k in line for k in ['PIN_TRACE','Fatal','INVALID_','MEMORY_INIT','COLD_TASK','PROBE_COMPLETE']):print(line,flush=True)
# Preserve exact vendor cell definitions for diagnosing reset/UDP/functional modes.
refs={c[0] for c in focus}
for model in sorted((root/'models').glob('*')):
    if not model.is_file():continue
    s=model.read_text(errors='replace')
    for ref in sorted(refs):
        pattern=r'\bmodule\s+'+re.escape(ref)+r'\b.*?\bendmodule\b'
        for definition in re.finditer(pattern,s,re.S):
            (probe/('Vendor_'+ref+'.v')).write_text(definition.group(0))
            important=[line.strip() for line in definition.group(0).splitlines() if re.search(r'\b(?:input|output|assign|always|initial)\b|udp|FUNCTIONAL|notifier',line,re.I)]
            print('VENDOR_MODEL '+ref+' '+str(model)+'\n'+'\n'.join(important[:16]),flush=True)
assert hashlib.sha256((system/'candidate.v').read_bytes()).hexdigest()==expected
print('COPY_REGISTER_PROBE_DIR='+str(probe),flush=True)
print('NO_RTL_NETLIST_CACHE_OR_ASSERTION_CHANGES',flush=True)
PY
