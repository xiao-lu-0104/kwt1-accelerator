import os
from pathlib import Path
import shutil
import subprocess
root = Path(__file__).resolve().parents[1]
base = root/'release/phase_runner_fixture'
package = base/'package'
for directory in ('rtl', 'tb', 'syn', 'tools', 'bin', 'models', 'runs'):
    (package/directory).mkdir(parents=True, exist_ok=True)
for directory, pattern in [('rtl','*.v'), ('rtl','*.vh'), ('tb','tb_kwt_*sram*.v'), ('tb','tb_kwt_*param*.v'), ('syn','*.tcl'), ('syn','*.sdc')]:
    for source in (root/directory).glob(pattern):
        shutil.copyfile(source, package/directory/source.name)
shutil.copyfile(root/'tb/tb_kwt_encoder_12.v', package/'tb/tb_kwt_encoder_12.v')
for name in ('tb_kwt_encoder_mmio.v','tb_kwt_encoder_axi.v'):
    shutil.copyfile(root/'tb'/name, package/'tb'/name)
shutil.copyfile(root/'tools/run_kwt_sram_binding.sh', package/'tools/run_kwt_sram_binding.sh')
(package/'sim/vectors/enc12').mkdir(parents=True,exist_ok=True)
(package/'sim/vectors/enc12/expect.mem').write_text('00\n')
(package/'sim/vectors/enc12/param_stream.mem').write_text('00000000\n')
for macro in ('RAMTP128X16','RAMTP1024X16'):
    target=package/'models'/macro/'verilog'
    target.mkdir(parents=True,exist_ok=True)
    (target/(macro+'.v')).write_text('// fixture only\n')
mock = '''#!/usr/bin/env bash
set -eu
args=" $* "
while (($#)); do if [[ "$1" == -top ]]; then top=$2; break; fi; shift; done
if [[ "$top" == tb_kwt_sram_phase ]]; then
    [[ "$args" != *+notimingcheck* ]] || exit 20
    if [[ "$SCENARIO" == compile ]]; then echo 'Error-[MOCK] first compiler error'; exit 1; fi
    marker='PASS: split-phase SRAM contract at 150MHz'
else
    [[ "$args" == *+notimingcheck* ]] || exit 21
    case "$top" in
        tb_kwt_packed_sram) marker='PASS: all SRAM shapes';;
        tb_kwt_param_stream) marker='PASS: parameter stream 256 records';;
        tb_kwt_encoder_param_load) marker='PASS: encoder parameter loading contract';;
        tb_kwt_encoder_mmio) marker='PASS: encoder MMIO channel ordering';;
        tb_kwt_encoder_axi) marker='PASS: encoder AXI MMIO 6336 values bit-exact';;
        tb_kwt_encoder_12*) marker='PASS: 12-layer encoder 6336 values bit-exact';;
        *) marker='PASS: all foundry adapter shapes';;
    esac
fi
printf '#!/usr/bin/env bash\n' > simv
if [[ "$SCENARIO" != missing ]]; then printf 'echo %q\n' "$marker" >> simv; fi
if [[ "$SCENARIO" == timing ]]; then printf 'echo "Timing violation: macro setuphold"\n' >> simv; fi
if [[ "$top" == tb_kwt_encoder_12 ]]; then
    cycles=3159181
    if [[ "$SCENARIO" == bad_cycles ]]; then cycles=3159182; fi
    printf 'echo "cycles=%s outputs=6336 "\n' "$cycles" >> simv
fi
if [[ "$top" == tb_kwt_encoder_12_stall ]]; then
    waits=5; words=90768
    if [[ "$SCENARIO" == missing_stalls ]]; then waits=0; fi
    if [[ "$SCENARIO" == short_stream ]]; then words=90766; fi
    printf 'echo "PARAM_TRANSFER accepted=45384 stalls=%s expected_cycles=3159186"\n' "$waits" >> simv
    printf 'echo "PARAM_SERIAL_WORDS accepted=%s"\n' "$words" >> simv
fi
if [[ "$top" == tb_kwt_encoder_axi ]]; then
    words=90768
    if [[ "$SCENARIO" == short_mmio ]]; then words=90766; fi
    printf 'echo "AXI_MMIO inputs=1584 parameter_words=%s output_words=1584 core_cycles=3300000 peripheral_cycles=3400000"\n' "$words" >> simv
fi
chmod +x simv
'''
(package/'bin/vcs').write_text(mock, newline='\n')
posix = '/'+str(package)[0].lower()+str(package)[2:].replace('\\','/')
for scenario in ('good','timing','missing','compile'):
    command=f'export PATH="{posix}/bin:$PATH"; export SCENARIO={scenario}; bash "{posix}/tools/run_kwt_sram_binding.sh" --suite unit --sram-root "{posix}/models" --output-parent "{posix}/runs"'
    result=subprocess.run(['C:/Program Files/Git/bin/bash.exe','-c',command],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (base/(scenario+'.log')).write_text(result.stdout)
    assert (result.returncode==0)==(scenario=='good'),result.stdout
    if scenario=='good': assert result.stdout.count('PASS:')==3,result.stdout
    if scenario=='timing': assert 'FAIL: macro timing/collision diagnostic' in result.stdout,result.stdout
    if scenario=='compile': assert 'Error-[MOCK] first compiler error' in result.stdout,result.stdout
    print('PASS: runner '+scenario)
for scenario in ('good','bad_cycles','missing_stalls','short_stream'):
    command=f'export PATH="{posix}/bin:$PATH"; export SCENARIO={scenario}; bash "{posix}/tools/run_kwt_sram_binding.sh" --param-handshake --sram-root "{posix}/models" --output-parent "{posix}/runs"'
    result=subprocess.run(['C:/Program Files/Git/bin/bash.exe','-c',command],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (base/('parameter_'+scenario+'.log')).write_text(result.stdout)
    assert (result.returncode==0)==(scenario=='good'),result.stdout
    if scenario=='good': assert result.stdout.count('PASS:')==7,result.stdout
    print('PASS: parameter runner '+scenario)
for suite,scenario in (('unit','good'),('full','good'),('full','short_mmio'),('full','missing')):
    command=f'export PATH="{posix}/bin:$PATH"; export SCENARIO={scenario}; bash "{posix}/tools/run_kwt_sram_binding.sh" --encoder-mmio --suite {suite} --sram-root "{posix}/models" --output-parent "{posix}/runs"'
    result=subprocess.run(['C:/Program Files/Git/bin/bash.exe','-c',command],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (base/('mmio_'+suite+'_'+scenario+'.log')).write_text(result.stdout)
    assert (result.returncode==0)==(scenario=='good'),result.stdout
    if scenario=='good':
        assert result.stdout.count('PASS:')==(2 if suite=='unit' else 3),result.stdout
        assert 'RUN: tb_kwt_encoder_12 ' not in result.stdout,result.stdout
    print('PASS: MMIO runner '+suite+' '+scenario)
result=subprocess.run(['C:/Program Files/Git/bin/bash.exe',str(root/'tools/run_kwt_sram_binding.sh'),'--encoder-mmio','--synth'],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
assert result.returncode==2 and 'synthesis is not configured' in result.stdout,result.stdout
print('PASS: MMIO runner rejects standalone-core synthesis')
