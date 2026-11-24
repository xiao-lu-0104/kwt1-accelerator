"""Select copied SMIC40 inputs and test them natively before retiring old runs."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from evaluate import load, save
from flow import tcl


def choose(records,suffix):
    candidates=[r for r in records if Path(r['source']).name.endswith(suffix)]
    if not candidates:raise ValueError('Missing cached input '+suffix)
    candidates.sort(key=lambda r:('/pr_saved/PR_VIEW/' in r['source'],Path(r['source']).stat().st_mtime))
    return candidates[-1]['cached']


def main():
    p=argparse.ArgumentParser();p.add_argument('cache',type=Path)
    p.add_argument('--dc',default='/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell')
    p.add_argument('--icc2',default='/eda/synopsys/icc2/icc2_2022.03-SP2-1/bin/icc2_shell')
    a=p.parse_args();cache=a.cache.resolve();records=load(cache/'Cache.json')['libraries']
    marker_path=cache/'NativeCacheReady.txt'
    if marker_path.exists():marker_path.unlink()
    ndms=[choose(records,n) for n in ['rvt.ndm','private.ndm','shared.ndm']]
    # Path names are preserved with a numeric prefix in the cache.
    tf=[r for r in records if r['kind']=='.tf']
    if not tf:raise ValueError('Missing technology TF')
    tf.sort(key=lambda r:('1P8M' in r['source'].upper(),Path(r['source']).stat().st_mtime))
    tf=tf[-1]['cached']
    dbs={}
    for r in records:
        if r['kind']=='.db':
            n=Path(r['source']).name
            if ('tt' in n.lower() and ('1p1' in n.lower() or '1p10' in n.lower())):dbs[n]=r['cached']
    if not any('scc40' in n.lower() for n in dbs) or not any('RAMSP1024X16' in n for n in dbs):
        raise ValueError('Missing copied TT standard/private SRAM DB')
    rc=choose(records,'StarRC_40LL_1P8M_1TM_TYP.tluplus')
    rcmap=choose(records,'StarRC_40LL_1P8M_1TM_cell.map')
    for label,exe,body,marker in [
        ('dc',a.dc,'\n'.join('read_db '+tcl(v) for v in dbs.values())+'\nputs "CACHE_DC_READ_OK"\n','CACHE_DC_READ_OK'),
        ('icc2',a.icc2,'create_lib '+tcl(cache/('probe_'+str(int(time.time()*1000000))+'.nlib'))+' -technology '+tcl(tf)+' -ref_libs [list '+' '.join(tcl(n) for n in ndms)+']\n'
         +'foreach R {RAMSP1024X16 RAMSP4096X16} {if {[sizeof_collection [get_lib_cells -quiet */$R]]!=1} {error "Cached macro reference unresolved: $R"}}\n'
         +'save_lib\nputs "CACHE_ICC2_READ_OK"\n','CACHE_ICC2_READ_OK')]:
        script=cache/('probe_'+label+'.tcl')
        script.write_text('if {[catch {\n'+body+'} Why]} {puts stderr "CACHE_ERROR: $Why";exit 2}\nexit 0\n')
        log=cache/('probe_'+label+'.log')
        with log.open('wb') as f:
            result=subprocess.call([exe,'-file' if label=='icc2' else '-f',str(script)],cwd=str(cache),stdout=f,stderr=subprocess.STDOUT)
        text=log.read_text(errors='replace')
        if result or marker not in text or '\nError:' in text:
            raise ValueError('Copied library native probe failed; old runs retained. Read '+str(log))
    save(cache/'Pdk.json',{'stdcell_db':next(v for n,v in dbs.items() if 'scc40' in n.lower()),
         'sram_dbs':[v for n,v in dbs.items() if 'RAM' in n], 'reference_ndms':ndms,
         'technology_tf':tf,'rc_tluplus':rc,'rc_map':rcmap})
    (cache/'NativeCacheReady.txt').write_text('NATIVE_PDK_CACHE_READY\n')
    print('NATIVE_PDK_CACHE_READY',cache/'Pdk.json')


if __name__=='__main__':main()
