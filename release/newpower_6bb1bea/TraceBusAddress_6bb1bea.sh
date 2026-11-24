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
probe=root/('address_probe_'+time.strftime('%Y%m%d_%H%M%S'))
probe.mkdir(exist_ok=False)
netlist=(root/'system/candidate.v').read_text(errors='replace')
domain='PowerTest.Dut.Backend.SystemResetN' if re.search(r'\bSystemResetN\b',netlist) else "1'bx"
code='`timescale 1ns/1fs\nmodule BootProbe;\ninteger N;\ninitial begin\nwait(PowerTest.ResetN===1\'b1);\nfor(N=0;N<800;N=N+1) begin\n @(negedge PowerTest.Clock);\n if(PowerTest.Dut.Backend.NiceRequestValid && PowerTest.Dut.Backend.NiceRequestReady)\n $display("ADDR_TRACE NICE inst=%h rs1=%h rs2=%h",PowerTest.Dut.Backend.NiceInst,PowerTest.Dut.Backend.NiceRs1,PowerTest.Dut.Backend.NiceRs2);\n if(PowerTest.Dut.Backend.Accelerator.Tpu.CopyRequestValid && PowerTest.Dut.Backend.Accelerator.Tpu.CopyRequestReady)\n $display("ADDR_TRACE COPY source=%h dest=%h words=%h",PowerTest.Dut.Backend.Accelerator.Tpu.CopySourceAddress,PowerTest.Dut.Backend.Accelerator.Tpu.CopyDestinationAddress,PowerTest.Dut.Backend.Accelerator.Tpu.CopyWordCount);\n if(PowerTest.Dut.Backend.DmaRequestValid)\n $display("ADDR_TRACE DMA ready=%b addr=%h read=%b mask=1111 bridge_in=%h bridge_saved=%h",PowerTest.Dut.Backend.DmaRequestReady,PowerTest.Dut.Backend.DmaRequestAddress,PowerTest.Dut.Backend.DmaRequestReadEnable,PowerTest.Dut.Backend.Accelerator.Bus.CopyDestinationAddress,PowerTest.Dut.Backend.Accelerator.Bus.CopyDestination);\n if(PowerTest.Dut.Backend.FabricRequestValid)\n $display("ADDR_TRACE ARBITER ready=%b addr=%h read=%b",PowerTest.Dut.Backend.FabricRequestReady,PowerTest.Dut.Backend.FabricRequestAddress,PowerTest.Dut.Backend.FabricRequestReadEnable);\n if(PowerTest.Dut.SystemRequestValid)\n $display("ADDR_TRACE SHARED ready=%b addr=%h read=%b",PowerTest.Dut.SystemRequestReady,PowerTest.Dut.SystemRequestAddress,PowerTest.Dut.SystemRequestReadEnable);\nend\n$display("BOOT_DIAGNOSTIC_COMPLETE");$finish;\nend\nendmodule\n'
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
result=subprocess.run([str(probe/'simv'),'+TASK=ff1','+SOURCE='+str(root/'ff1/source.hex'),'+EXPECTED='+str(root/'ff1/expected.hex'),'+SAIF='+str(run/'unused.saif')],cwd=str(run),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(run/'native.log').write_bytes(result.stdout)
print('DIAGNOSTIC_SIMULATION_EXIT='+str(result.returncode),flush=True)
lines=(run/'native.log').read_text(errors='replace').splitlines()
for line in lines:
    if any(k in line for k in ('ADDR_TRACE ','MEMORY_INIT','Warning','Error','BOOT_DIAGNOSTIC_COMPLETE')) or 'time scale' in line.lower():print(line,flush=True)
print('BOOT_PROBE_DIR='+str(probe),flush=True)
print('ORIGINAL_SYSTEM_NETLIST_CACHE_AND_FAILED_LOGS_UNCHANGED',flush=True)
BOOT_DIAG
