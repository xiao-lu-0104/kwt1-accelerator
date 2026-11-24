"""Recreate missing macro DBs from original vendor TT Liberty before cleanup."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def save(p,d):p.write_text(json.dumps(d,indent=2)+'\n')


def main():
    cache=Path('/tmp/final_7cf5155_pdk_'+str(os.getuid()))
    ledger=json.loads((cache/'Cache.json').read_text())
    folder=cache/'new_macro_db';folder.mkdir(exist_ok=True)
    tool=shutil.which('lc_shell') or '/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell'
    for ref in ['RAMSP1024X16','RAMSP4096X16']:
        src=Path('/storage1/admin_public_dir/SRAM_Lib_2025')/ref/'lib'/(ref+'_tt_1p10v_1p10v_25c.lib')
        if not src.is_file():raise RuntimeError('Vendor Liberty missing: '+str(src))
        if ref=='RAMSP1024X16' and sha(src)!='7cf092257dfe18f32affee2d1a071b198b7cc68cb50b5bc71b0fdc98a79cfdb1':
            raise RuntimeError('Reviewed private macro Liberty changed; stop before deletion')
        dest=folder/(ref+'_tt_1p10v_1p10v_25c.db')
        text=src.read_text(errors='replace');match=re.search(r'library\s*\(\s*"?([^"\s\)]+)',text)
        if not match:raise RuntimeError('Missing Liberty library name')
        if not dest.exists():
            tcl=folder/(ref+'.tcl')
            body='read_lib {'+str(src)+'}\nwrite_lib {'+match.group(1)+'} -format db -output {'+str(dest)+'}\n'
            body+='if {![file isfile {'+str(dest)+'}] || [file size {'+str(dest)+'}]==0} {error "No DB produced"}\n'
            tcl.write_text('if {[catch {\n'+body+'puts "MACRO_DB_COMPLETE"\n} Why]} {puts stderr "MACRO_DB_ERROR: $Why";exit 2}\nexit 0\n')
            log=folder/(ref+'.log')
            with log.open('wb') as f:
                result=subprocess.call([tool,'-f',str(tcl)],cwd=str(folder),stdout=f,stderr=subprocess.STDOUT)
            output=log.read_text(errors='replace')
            if result or 'MACRO_DB_COMPLETE' not in output or '\nError:' in output:
                print(output[-7000:]);raise RuntimeError('Macro conversion failed; old files retained: '+str(log))
        if not dest.is_file() or not dest.stat().st_size:raise RuntimeError('Empty macro DB')
        ledger['libraries']=[r for r in ledger['libraries'] if r.get('cached')!=str(dest)]
        ledger['libraries'].append({'source':str(dest),'cached':str(dest),'kind':'.db','sha256':sha(dest),
            'vendor_lib':str(src),'vendor_lib_sha256':sha(src),'conversion_tool':tool})
        print('MACRO_DB_READY',dest,flush=True)
    ledger['status']='COPIED_AND_REBUILT_MACRO_DBS_NATIVE_PROBE_PENDING'
    save(cache/'Cache.json',ledger)
    plan=json.loads((cache/'CleanupPlan.json').read_text())
    plan['cache_manifest_sha256']=sha(cache/'Cache.json');save(cache/'CleanupPlan.json',plan)
    marker=cache/'NativeCacheReady.txt'
    if marker.exists():marker.unlink()
    print('PDK_DB_REPAIR_COMPLETE; proceeding to actual read test')
    subprocess.check_call(['python3','/tmp/submission_20261113/probe_cache.py',str(cache)])
    subprocess.check_call(['python3','/tmp/submission_20261113/clean_server.py','apply','--plan',str(cache/'CleanupPlan.json')])
    (cache/'CleanupComplete.txt').write_text('COMPLETE\n')
    print('CLEANUP_7CF5155_COMPLETE')


if __name__=='__main__':main()
