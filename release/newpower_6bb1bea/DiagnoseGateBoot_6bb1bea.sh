#!/usr/bin/env bash
set -euo pipefail
python3 - <<'BOOT_DIAG'
from pathlib import Path
import ast, json, os, re, subprocess, sys, time
root=Path('/tmp/final_power_6bb1bea_'+str(os.getuid()))
print('DIAGNOSTIC_ROOT='+str(root),flush=True)
for name,head,tail in [('system/Metrics.tsv',30,0),('ff1/MemoryInit.sv',9,5),('ff1/native.log',35,3)]:
    path=root/name
    print('\nFILE: '+name,flush=True)
    if not path.is_file():print('MISSING',flush=True);continue
    lines=path.read_text(errors='replace').splitlines()
    print('\n'.join(lines[:head]),flush=True)
    if tail:print('\n'.join(lines[-tail:]),flush=True)
probe=root/('boot_probe_'+time.strftime('%Y%m%d_%H%M%S'))
probe.mkdir(exist_ok=False)
netlist=(root/'system/candidate.v').read_text(errors='replace')
domain='PowerTest.Dut.Backend.SystemResetN' if re.search(r'\bSystemResetN\b',netlist) else "1'bx"
code='''`timescale 1ns/1fs
module BootProbe;
integer N;
initial begin
    $printtimescale(PowerTest);
    $printtimescale(PowerTest.Init);
    for(N=0;N<600;N=N+1) begin
        @(negedge PowerTest.Clock);
        if(N<65 || N%50==0)
            $display("BOOT_PROBE n=%0d time_ns=%.6f init=%b tb_resetn=%b dut_resetn=%b domain_resetn=%b pc=%h fetch_req=%b itcm_req=%b dtcm_req=%b sys_req=%b",N,$realtime,
            PowerTest.Init.Done,PowerTest.ResetN,PowerTest.Dut.ResetN,DOMAIN,
            PowerTest.Dut.CpuPc,PowerTest.Dut.FetchRequestValid,PowerTest.Dut.ItcmRequestValid,PowerTest.Dut.DtcmRequestValid,PowerTest.Dut.SystemRequestValid);
    end
    $display("BOOT_DIAGNOSTIC_COMPLETE");
    $finish;
end
endmodule
'''.replace('DOMAIN',domain)
(probe/'BootProbe.sv').write_text(code)
tree=ast.parse((root/'ff1/compile/Compile.py').read_text())
commands=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cmd' for t in n.targets)]
assert len(commands)==1,'Missing original VCS command'
cmd=commands[0]
cmd[cmd.index('-o')+1]=str(probe/'simv')
cmd += [str(probe/'BootProbe.sv'),'-top','BootProbe']
build=probe/'compile';build.mkdir()
helper=build/'CompileProbe.py'
helper.write_text('import os,subprocess\ncmd='+repr(cmd)+'\nsubprocess.check_call(cmd)\nassert os.access('+repr(str(probe/'simv'))+',os.X_OK)\nprint("BOOT_PROBE_COMPILED")\n')
sys.path.insert(0,str(root/'tools'))
from NativeHelpers import native
print('BOOT_PROBE_DIR='+str(probe),flush=True)
native(['python3',str(helper)],build,'BOOT_PROBE_COMPILED')
run=probe/'run';run.mkdir()
native([str(probe/'simv'),'+TASK=ff1','+SOURCE='+str(root/'ff1/source.hex'),'+EXPECTED='+str(root/'ff1/expected.hex'),'+SAIF='+str(run/'unused.saif')],run,'BOOT_DIAGNOSTIC_COMPLETE')
lines=(run/'native.log').read_text(errors='replace').splitlines()
for line in lines:
    if any(k in line for k in ('BOOT_PROBE ','MEMORY_INIT','Warning','Error','BOOT_DIAGNOSTIC_COMPLETE')) or 'time scale' in line.lower():print(line,flush=True)
print('BOOT_PROBE_DIR='+str(probe),flush=True)
print('ORIGINAL_SYSTEM_NETLIST_CACHE_AND_FAILED_LOGS_UNCHANGED',flush=True)
BOOT_DIAG
