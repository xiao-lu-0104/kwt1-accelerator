"""Synthesize the reviewed 6bb1bea accelerator plus NICE/ICB32 and private SRAM."""
import argparse
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'tools'))
from NativeHelpers import load,save,sha,native,tcl


def metric(path):return dict(line.split('\t',1) for line in path.read_text().splitlines() if '\t' in line)


def config(path,root,pdk,mode,baseline=None):
    sources=load(root/'AcceleratorSources.json')
    lines=['set Top SubmissionAccelerator','set SourceCommit 6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6',
           'set StdDb '+tcl(pdk['stdcell_db']),
           'set SramDbs [list '+' '.join(tcl(p) for p in pdk['sram_dbs'])+']',
           'set Sources [list '+' '.join(tcl(root/n) for n in sources)+']',
           'set Includes {}','set Defines {SYNTHESIS TPU_SRAM_MODEL TPU_MATRIX_ROWS=2}',
           'set ConstraintFile '+tcl(root/'integration/Constraints.tcl'),
           'set ClockPort Clock','set ExpectedPeriod 6.666667','set MacroCounts {RAMSP1024X16 56}',
           'set Mode '+mode,'set Tools '+tcl(HERE/'tools')]
    if baseline:lines.append('set BaselineDdc '+tcl(baseline))
    (path/'Config.tcl').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path)
    p.add_argument('--cache',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();cache=a.cache.resolve()
    pdk=load(cache/'Pdk.json')
    if not (cache/'NativeCacheReady.txt').is_file():raise ValueError('Cache not natively verified; cleanup/DC not authorized to continue')
    provenance=load(root/'SourceManifest.json')
    if provenance['source_commit']!='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6':raise ValueError('Wrong frontend payload')
    for name,digest in provenance['files_sha256'].items():
        if sha(root/name)!=digest:raise ValueError('Source payload changed: '+name)
    dc='/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell'
    if not os.access(dc,os.X_OK):raise ValueError('DC executable missing')
    # The candidate is accepted only after native timing checks. No old design
    # netlist, DDC, SAIF, TCM wrapper or old launcher is used as the new design.
    out=root/'dc_accelerator'
    if (out/'Accepted.json').is_file():print('ALREADY_COMPLETE',out);return
    if not out.exists():
        out.mkdir();config(out,root,pdk,'compile')
        native([dc,'-f',str(HERE/'tools/Dc.tcl')],out,'DC_REPORTS_COMPLETE')
    elif not (out/'Metrics.tsv').is_file():
        raise ValueError('Previous attempt retained; inspect '+str(out/'native.log')+' before retrying')
    data=metric(out/'Metrics.tsv');accepted=out
    if float(data['hold_wns_ns'])<0 and float(data['setup_wns_ns'])>=0:
        recovery=root/'hold_accelerator'
        if not recovery.exists():
            recovery.mkdir();config(recovery,root,pdk,'hold',out/'baseline.ddc')
            native([dc,'-f',str(HERE/'tools/Dc.tcl')],recovery,'DC_REPORTS_COMPLETE')
        if not (recovery/'Metrics.tsv').is_file():raise ValueError('Hold recovery incomplete; keep baseline')
        data=metric(recovery/'Metrics.tsv');accepted=recovery
    print('CURRENT_SOURCE: 6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6')
    print('SCORING_SCOPE: 16 MAC: TpuNice + TpuFf1Stream + TpuLocalCopy/core + TpuIcb + 56 private SRAM; CPU/shared SRAM and new SystemBus arbiter excluded')
    for k,v in data.items():print(k+': '+v)
    if min(float(data['setup_wns_ns']),float(data['hold_wns_ns']))<0:
        raise ValueError('Native reports saved but timing fails; do not substitute old results')
    save(accepted/'Accepted.json',{'source_commit':provenance['source_commit'],'status':'ACCELERATOR_DC_TIMING_REPORTS_COMPLETE_FUNCTIONAL_REVIEW_PENDING',
        'netlist_sha256':sha(accepted/'candidate.v'),'metrics':data})
    print('NEW_6BB1BEA_ACCELERATOR_DC_REPORTS_COMPLETE')
    print('ACCEPTED_DIR='+str(accepted))
    print('NEXT: new platform system integration and fresh cold-task gate/SAIF validation; not yet performed')


if __name__=='__main__':
    try:main()
    except Exception as e:print('NEW_DC_STOPPED:',e,file=sys.stderr);sys.exit(2)
