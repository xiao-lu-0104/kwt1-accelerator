"""Finish an existing successful DC report, recognizing native serialized SDC syntax."""
import argparse
import json
from pathlib import Path
from Prepare import check,sha
from ClockPortReview import finish


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    out=parser.parse_args().out.resolve(); tools=Path(__file__).resolve().parent
    check(json.loads((out/'Inputs.json').read_text()))
    if (out/'ClockPortSummary.json').exists() or (out/'ClockPortReports.partial.tar.gz').exists():
        raise ValueError('Existing completed output retained; refusing overwrite')
    required=('Inputs.json','dc.log','summary.txt','loaded.sdc','clock_ports_corrected.sdc',
        'area_breakdown.tsv','area_totals.txt','clock_port_sources.txt','setup.rpt','hold.rpt')
    before={str(out/name):sha(out/name) for name in required}
    recovery={'reason':'Native DC write_sdc puts target first and may omit default divide-by 1',
        'mode':'Summary/SDC semantics verification/archive only; no EDA or simulation',
        'inputs':before,'recovery_tools':{str(p):sha(p) for p in tools.iterdir() if p.is_file()}}
    target=out/'ClockReviewRecoveryInputs.json'
    if target.exists(): raise ValueError('Recovery input record already exists; refusing overwrite')
    target.write_text(json.dumps(recovery,indent=2)+'\n')
    print('RECOVERY: original inputs verified; original raw report files fingerprinted; no DC rerun',flush=True)
    finish(out)
    check({'inputs':before}); check({'inputs':recovery['recovery_tools']})
    print('RECOVERY_RAW_REPORTS_UNCHANGED: PASS',flush=True)


if __name__=='__main__': main()
