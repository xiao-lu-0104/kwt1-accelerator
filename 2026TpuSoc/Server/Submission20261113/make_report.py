"""Fill new-report numeric macros only from paired native result files."""
import argparse
import math
from pathlib import Path
from evaluate import load,save,sha


def metrics(path):
    return dict(line.split('\t',1) for line in Path(path).read_text().splitlines() if '\t' in line)


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    p.add_argument('--dc',type=Path,required=True);p.add_argument('--power',type=Path,required=True)
    p.add_argument('--pr',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();c=load(a.config);d=metrics(a.dc/'Metrics.tsv');power=load(a.power/'PowerSummary.json')
    if not c['frontend_bound'] or d['source_commit']!=c['source_commit'] or power['source_commit']!=c['source_commit']:
        raise ValueError('Report inputs belong to different revisions')
    if load(a.dc/'Complete.json')['target']!='accelerator':raise ValueError('Use accelerator area, not E203 total area')
    if len(power['tasks'])!=12:raise ValueError('Publish the complete 12-task mandatory batch')
    # The reviewer resolves real default/propagated/X coverage; generating a PDF
    # cannot itself certify activity quality.
    review=load(a.power/'CoverageReview.json')
    if review.get('source_commit')!=c['source_commit'] or review.get('status')!='ACCEPTED':
        raise ValueError('Power coverage/X review not completed')
    for name,digest in review['reports_sha256'].items():
        if sha(a.power/name)!=digest:raise ValueError('Reviewed power evidence changed')
    area=float(d['mapped_leaf_area_um2'])/1e6;sram=float(d['sram_area_um2'])/1e6
    setup=float(d['setup_wns_ns']);hold=float(d['hold_wns_ns'])
    if min(setup,hold)<0:raise ValueError('DC timing still fails; do not publish passing results')
    values={'AccelArea':area,'LogicArea':area-sram,'PrivateArea':sram,'SetupSlack':setup,'HoldSlack':hold,
            'SystemPower':power['average_power_w']*1000,'TaskEnergy':power['energy_per_task_j']*1e6,
            'AccelPower':sum(t['accelerator_power_w']*t['duration_seconds'] for t in power['tasks'])/
                         sum(t['duration_seconds'] for t in power['tasks'])*1000}
    if any(not math.isfinite(x) for x in values.values()):raise ValueError('Non-finite result')
    lines=['% Generated from current paired native reports.','\\ResultsReadytrue']
    for k,v in values.items():lines.append('\\renewcommand{\\'+k+'}{'+format(v,'.9g')+'}')
    if a.pr:
        for stage in ['01_import_io','02_pg_place','03_build_clock','04_route_clock','05_route','06_export']:
            r=load(a.pr/stage/'Complete.json')
            if r['source_commit']!=c['source_commit']:raise ValueError('PR revision mismatch')
        lines.append('\\PrReadytrue')
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'results.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save(a.out/'ReportInputs.internal.json',{'source_commit':c['source_commit'],
        'dc':str(a.dc),'power':str(a.power),'pr':str(a.pr) if a.pr else None,
        'public_report_excludes':'server paths, internal versions, E203 total area, identity checks and historical troubleshooting'})
    print('REPORT_RESULTS_FILLED',a.out/'results.tex')


if __name__=='__main__':main()
