"""Bounded current task simulations followed by SAIF-annotated report-only power."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from Tasks import check_record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);a=p.parse_args()
    out=a.out.resolve();tools=out/'tools';stage='prepare'
    def run(label,limit,log,command):
        print('STAGE:',label,flush=True)
        code=subprocess.call(['python3',str(tools/'StageWatch.py'),'--label',label,'--limit',str(limit),
            '--log',str(log),'--cwd',str(out),'--']+command)
        if code:
            print(log.read_text(errors='replace')[-6500:])
            raise ValueError('Stage failed: '+label+' exit='+str(code))
    success=False
    try:
        run('prepare_current_tasks',300,out/'prepare.log',['python3',str(tools/'Tasks.py'),'prepare',str(out)])
        inputs=json.loads((out/'Inputs.json').read_text())
        vcs=os.environ.get('VCS_BIN') or shutil.which('vcs') or '/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs'
        if not Path(vcs).is_file(): raise ValueError('VCS executable unavailable: '+vcs)
        stage='compile'
        command=[vcs,'-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext','+define+FPGA+FPGA_SOURCE',
            '+notimingcheck','+delay_mode_zero','+vcs+saif_libcell','-f',str(out/'Task.f')]
        for name in ('GateResetInventory.sv','IcbMirror.sv','EffectiveDataGuard.sv','SystemActivity.sv','SharedTcmGuard.sv'):
            command.append(str(out/name))
        command.append(str(tools/'TcmInitializer.sv'))
        for top in ('SharedTest','GateResetInventory','IcbMirror','EffectiveDataGuard','TaskActivity','SharedTcmGuard','TcmInitializer'):
            command+=['-top',top]
        command+=['-o',str(out/'simv')]
        run('compile_current_tasks',900,out/'compile.log',command)
        for name in ('ff1','encoder'):
            stage=name+'_simulation';case=out/name;case.mkdir()
            vectors=Path(inputs['bundle'])/'Vectors'
            if name=='ff1':vectors=vectors/'Ff1_normal'
            run(stage,1200 if name=='ff1' else 2700,case/'run.log',[str(out/'simv'),'+INIT_ALL=1','+INIT_PATTERN=2',
                '+RESET_X_LIST='+str(case/'reset_x.txt'),'+TASK_SAIF='+str(case/'task.saif'),
                '+FIRMWARE='+inputs['firmware'],'+VECTORS='+str(vectors),'+KIND='+('1' if name=='ff1' else '0'),'+LAYERS=1'])
            run('validate_'+name,300,case/'validate.log',['python3',str(tools/'Tasks.py'),'validate',str(out),'--task',name])
            print((case/'validate.log').read_text(),flush=True)
        for name in ('ff1','encoder'):
            stage=name+'_power'
            run(stage,1000,out/(name+'_power_runner.log'),['python3',str(tools/'Power.py'),str(out),'--task',name])
            print((out/(name+'_power_runner.log')).read_text(),flush=True)
        check_record(out/'Inputs.json')
        data={name:json.loads((out/name/'PowerSummary.json').read_text()) for name in ('ff1','encoder')}
        (out/'CurrentPowerSummary.json').write_text(json.dumps({'tasks':data,
            'result':'CURRENT_SYSTEM_TASK_POWER_REPORTS_COMPLETE_REVIEW_PENDING',
            'scope':'new 20261109 system, TT pre-layout tasks; no old SAIF reuse; default/X/boundary review remain'},indent=2)+'\n')
        success=True
        print('RESULT: CURRENT_SYSTEM_TASK_POWER_REPORTS_COMPLETE_REVIEW_PENDING',flush=True)
    except Exception as error:
        print('CURRENT_POWER_ERROR:',error,flush=True)
        print('RESULT: CURRENT_POWER_INCOMPLETE stage='+stage,flush=True)
    finally:
        with tarfile.open(str(out/'CurrentPowerReports.partial.tar.gz'),'w:gz') as archive:
            for path in sorted(out.rglob('*')):
                if any(part in ('csrc','__pycache__') or part.endswith('.daidir') for part in path.parts):continue
                if path.is_file() and path.name not in ('CurrentPowerReports.partial.tar.gz','simv','runner.log'):
                    archive.add(str(path),arcname=str(path.relative_to(out)),recursive=False)
        print('WORK_DIR:',out,flush=True)
    if not success:raise SystemExit(2)


if __name__=='__main__':main()
