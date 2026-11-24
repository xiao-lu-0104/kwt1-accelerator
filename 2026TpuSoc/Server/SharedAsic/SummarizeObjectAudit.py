"""Summarize actual DDC connectivity without declaring unknown activity harmless."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from PrepareObjectAudit import check


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    args=parser.parse_args(); out=args.out.resolve()
    check(json.loads((out/'ObjectAuditInputs.json').read_text()))
    summary={}
    for task in ('ff1','encoder'):
        case=out/task
        rows=list(csv.DictReader((case/'object_connections.tsv').open(),delimiter='\t'))
        requests=list(csv.DictReader((case/'objects.tsv').open(),delimiter='\t'))
        if len(rows)!=len(requests) or {r['id'] for r in rows}!={r['id'] for r in requests}:
            raise ValueError('Object query output incomplete')
        for row,request in zip(rows,requests):
            if (row['id'],row['name'])!=(request['id'],request['name']): raise ValueError('Query identity changed')
        counts=Counter(row['status'] for row in rows)
        unknown=[r for r in rows if 'TX_NONZERO' in r['reason']]
        terminal=[r for r in unknown if r['status']=='NET_FOUND' and r['input_pins']=='0'
                  and r['inout_pins']=='0' and r['top_ports']=='0' and r['port_query']=='OK']
        consumed=[r for r in unknown if r['status']=='NET_FOUND' and
                  (int(r['input_pins'])>0 or int(r['inout_pins'])>0 or int(r['top_ports'])>0)]
        drivers=Counter(ref for r in consumed for ref in r['driver_refs'].split(',') if ref)
        sinks=Counter(ref for r in consumed for ref in r['sink_refs'].split(',') if ref)
        data={'statuses':dict(counts),'unknown_requests':len(unknown),
              'unknown_net_no_direct_loads':len(terminal),'unknown_net_with_connections':len(consumed),
              'unknown_no_load_proof_limit':'Direct connectivity only; not a functional/energy waiver',
              'driver_reference_counts':dict(drivers.most_common()),'sink_reference_counts':dict(sinks.most_common())}
        summary[task]=data
        print('ACTIVITY_OBJECT_SUMMARY:',task,json.dumps(data,sort_keys=True))
        for row in consumed[:12]: print('CONNECTED_UNKNOWN:',task,json.dumps(row,sort_keys=True))
        for row in terminal[:5]: print('NO_DIRECT_LOAD_UNKNOWN:',task,json.dumps(row,sort_keys=True))
        for row in [r for r in rows if r['status']=='ABSENT_FROM_DDC_INDEX'][:8]:
            print('DDC_OBJECT_ABSENT:',task,json.dumps(row,sort_keys=True))
        for name in ('activity_detail.rpt','PWR19_manual.txt','get_switching_activity_help.txt'):
            path=case/name
            if path.exists():
                lines=path.read_text(errors='replace').splitlines()
                print('OBJECT_REPORT_BEGIN:',task,name)
                print('\n'.join(lines[:55]))
                print('OBJECT_REPORT_END')
        for path in sorted(case.glob('clock_*_*.txt')):
            if path.name.endswith('.error.txt'): continue
            print('CLOCK_OBJECT_ACTIVITY:',task,path.name,path.read_text(errors='replace').strip()[:1000])
    (out/'ObjectAuditSummary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('SYSTEM_POWER_STATUS: CPU/interconnect/shared SRAM still pending; no X/default override performed')


if __name__=='__main__': main()
