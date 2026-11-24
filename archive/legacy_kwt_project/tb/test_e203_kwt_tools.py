"""Offline control-flow checks, NOT CPU simulation. Run with Git Bash installed."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    bash = shutil.which('bash')
    if os.name == 'nt':
        bash = 'C:/Program Files/Git/bin/bash.exe'
    if not bash:
        raise RuntimeError('Bash required')
    base = ROOT/'release/e203_runner_fixture'
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as name:
        package = Path(name).resolve()
        for folder in ('tools','platform','bin','runs','models','rtl','tb','sim/vectors/enc12','images/smoke','images/full'):
            (package/folder).mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT/'external/e203_hbirdv2/rtl/e203', package/'platform', dirs_exist_ok=True)
        cfg = package/'platform/core/config.v'
        original = cfg.read_text()
        import re
        cfg.write_text(re.sub(r'(?m)^(`define E203_CFG_(?:I|D)TCM_ADDR_WIDTH)\s+16\s*$', r'\1 18', original), encoding='utf-8')
        source = package/'platform/subsys/e203_subsys_mems.v'
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        for file in ('run_e203_kwt.sh','prepare_e203_kwt.py'):
            shutil.copyfile(ROOT/'tools'/file,package/'tools'/file)
        for pattern in ('*.v','*.vh'):
            for path in (ROOT/'rtl').glob(pattern):
                shutil.copyfile(path,package/'rtl'/path.name)
        shutil.copyfile(ROOT/'tb/tb_kwt_e203.v',package/'tb/tb_kwt_e203.v')
        for kind in ('smoke','full'):
            for file in ('itcm.mem','dtcm.mem','program.elf','build.json','kwt_e203_images.vh'):
                (package/'images'/kind/file).write_text('// fixture, no real program\n')
        (package/'sim/vectors/enc12/expect.mem').write_text('00\n')
        for macro in ('RAMTP128X16','RAMTP1024X16'):
            path=package/'models'/macro/'verilog'/ (macro+'.v')
            path.parent.mkdir(parents=True)
            path.write_text('// mock only\n')
        mock='''#!/usr/bin/env bash
set -eu
case " $* " in *DISABLE_SV_ASSERTION*) exit 9;; esac
while (($#));do if [[ "$1" == -o ]];then simulator=$2;break;fi;shift;done
if [[ "$SCENARIO" == compile ]];then echo 'Error-[MOCK] compile failure';exit 1;fi
cat > "$simulator" <<'SIM'
#!/usr/bin/env bash
if [[ " $* " == *SMOKE=1* ]];then
    if [[ "$SCENARIO" == smoke_fail ]];then echo 'Fatal: CPU smoke failed';exit 0;fi
    echo 'CPU_SMOKE instructions=123 input_words=1'
    echo 'PASS: E203 CPU boot / C program / ICB-AXI MMIO / input / reset'
else
    if [[ "$SCENARIO" != missing_metrics ]];then
        words=90768
        if [[ "$SCENARIO" == short_transfer ]];then words=90766;fi
        echo "CPU_TASK inputs=1584 parameter_words=$words output_words=1584 core_cycles=4000000 peripheral_cycles=4100000 cpu_cycles=4200000 instructions=1234567"
    fi
    echo 'PASS: E203 CPU C driver full encoder / 6336 shared-memory bytes bit-exact'
    if [[ "$SCENARIO" == runtime_error ]];then echo 'Error: hidden runtime error';fi
fi
SIM
chmod +x "$simulator"
'''
        (package/'bin/vcs').write_text(mock, encoding='ascii', newline='\n')
        posix = str(package).replace('\\','/')
        if os.name=='nt':
            posix='/'+posix[0].lower()+posix[2:]
        for scenario in ('good','compile','smoke_fail','missing_metrics','short_transfer','runtime_error'):
            cmd=('export PATH="{p}/bin:$PATH";export SCENARIO={s};bash "{p}/tools/run_e203_kwt.sh" '
                 '--platform "{p}/platform_parent" --sram-root "{p}/models" --output-parent "{p}/runs"').format(p=posix,s=scenario)
            # Match the runner's platform discovery without modifying its code.
            source_root=package/'platform_parent/rtl'
            source_root.mkdir(parents=True,exist_ok=True)
            if not (source_root/'e203').exists():
                shutil.copytree(package/'platform',source_root/'e203')
            result=subprocess.run([bash,'-c',cmd],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            (base/(scenario+'.log')).write_text(result.stdout,encoding='utf-8')
            assert (result.returncode==0)==(scenario=='good'),result.stdout
            if scenario=='good':
                assert result.stdout.count('PASS:')==2,result.stdout
            assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
            assert hashlib.sha256((source_root/'e203/subsys/e203_subsys_mems.v').read_bytes()).hexdigest()==original_hash
            print('PASS: E203 runner fixture '+scenario)
        # A platform with the wrong capacity must fail before editing anything.
        bad_cfg=source_root/'e203/core/config.v'
        bad_cfg.write_text(original,encoding='utf-8')
        result=subprocess.run([bash,'-c',cmd.replace('runtime_error','good')],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        assert result.returncode!=0 and 'capacity will not be changed' in result.stdout,result.stdout
        print('PASS: E203 runner refuses unexpected TCM capacity')


if __name__=='__main__':
    main()
