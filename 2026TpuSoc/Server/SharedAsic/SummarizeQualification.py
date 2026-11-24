"""Verify each independent qualification result, without granting power acceptance."""
import argparse
import json
from pathlib import Path
import re
from PrepareQualification import check


def task_status(text,task):
    kind,values,cycles=(1,25344,332348) if task=='ff1' else (0,6336,1485712)
    required=(f'PASS SHARED: kind={kind} layers=1 values={values} cycles={cycles} ',
              'released=1 checked=1 new_control_QX=0',
              'ICB_MIRROR_FINAL: divergence_observed=0',
              'PASS EFFECTIVE_DATA_GUARD:', 'EFFECTIVE_GUARD_FINAL: complete=1')
    return all(s in text for s in required) and not re.search(r'Fatal:|FATAL:|Error-\[|FAIL:',text)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    args=parser.parse_args(); out=args.out.resolve()
    check(json.loads((out/'QualificationInputs.json').read_text()))
    summary={}
    smoke=(out/'macro/run.log').read_text(errors='replace') if (out/'macro/run.log').exists() else ''
    summary['shared_macro_smoke']=('PASS' if (out/'macro/status.txt').read_text().strip()=='PASS'
        and 'PASS SHARED_MACRO_SMOKE:' in smoke else 'FAIL')
    print('QUALIFICATION_MACRO:',summary['shared_macro_smoke'])
    for task in ('ff1','encoder'):
        case=out/task
        text=(case/'run.log').read_text(errors='replace')
        status='PASS' if (case/'status.txt').read_text().strip()=='PASS' and task_status(text,task) else 'FAIL'
        clock='PASS' if (case/'clock_status.txt').read_text().strip()=='PASS' else 'FAIL'
        summary[task]={'effective_data_guard':status,'clock_query':clock}
        print('QUALIFICATION_TASK:',task,'guard='+status,'clock_query='+clock)
        for line in text.splitlines():
            if line.startswith(('EFFECTIVE_DATA_SUMMARY:','MACRO_INPUT_SUMMARY:','PASS SHARED:')):
                print(task,line)
        path=case/'clocks.txt'
        if path.exists():
            for line in path.read_text(errors='replace').splitlines()[:4]:
                print('CLOCK_ACTIVITY:',task,line[:500])
    summary['power_acceptance']='PENDING; qualified functional consumption does not bound idle X power'
    summary['system_power']='PENDING CPU/interconnect/shared SRAM implementation and activity'
    (out/'QualificationSummary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('POWER_ACCEPTANCE: PENDING; no X/default waiver, system total not established')


if __name__=='__main__': main()
