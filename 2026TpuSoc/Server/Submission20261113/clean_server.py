"""Retire old user runs only after copying reusable PDK inputs outside the runs.

Run from HOME, never from a directory selected for deletion. --apply executes
the concrete saved plan; it does not expand a new wildcard deletion target.
No process is killed and no administrator/shared directory is deleted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

EXTENSIONS=('.db','.tf','.tluplus','.map','.lef')
SELF=Path(__file__).resolve()


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def under(path,parent):
    try:path.relative_to(parent);return True
    except ValueError:return False


def dump(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def active(targets):
    blocked=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:
            if proc.stat().st_uid!=os.getuid():continue
            values=[]
            try:values.append(os.readlink(str(proc/'cwd')))
            except OSError:pass
            values.append((proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace'))
            try:
                for fd in (proc/'fd').iterdir():
                    try:values.append(os.readlink(str(fd)))
                    except OSError:pass
            except OSError:pass
            for target in targets:
                if any(str(target) in text for text in values):
                    blocked.append({'pid':int(proc.name),'target':str(target)})
        except (OSError,PermissionError):continue
    return blocked


def roots_and_targets():
    home=Path.home().resolve();soc=home/'soc';targets=[]
    if soc.is_dir():
        for p in soc.iterdir():
            # Keep the new preparation toolkit. All previous sources, runs and
            # old result archives are otherwise retired as requested.
            if p.name=='submission_20261113' or under(SELF,p.resolve()):continue
            if p.lstat().st_uid!=os.getuid():continue
            if p.is_symlink():raise RuntimeError('Inspect top-level symlink before cleanup: '+str(p))
            if p.resolve().parent!=soc:raise RuntimeError('Unsafe soc target '+str(p))
            targets.append(p.resolve())
    for p in Path('/tmp').iterdir():
        if p.name.startswith(('tpusoc_','kwt_')) and not p.is_symlink() and p.is_dir() and p.stat().st_uid==os.getuid():
            targets.append(p.resolve())
    return soc,targets


def discover(targets):
    found=set()
    def add(raw):
        if not isinstance(raw,str) or not raw.startswith('/'):return
        p=Path(raw)
        if p.name.endswith('.ndm') and p.is_dir():found.add(p.resolve())
        elif p.suffix in EXTENSIONS and p.is_file():found.add(p.resolve())
    def walk_json(obj):
        if isinstance(obj,dict):
            for k,v in obj.items():add(k);walk_json(v)
        elif isinstance(obj,list):
            for v in obj:walk_json(v)
        else:add(obj)
    for target in targets:
        if not target.is_dir():continue
        for current,dirs,files in os.walk(str(target),followlinks=False):
            current=Path(current)
            for name in list(dirs):
                child=current/name
                if child.is_symlink():
                    dirs.remove(name)
                    if name.endswith('.ndm'):add(str(child.resolve()))
                elif name.endswith('.ndm'):
                    found.add(child.resolve());dirs.remove(name)
                elif name.endswith('.nlib') or name in ('work','build','simv.daidir','csrc'):
                    dirs.remove(name)
            for name in files:
                p=current/name
                if p.suffix in EXTENSIONS and not p.is_symlink():found.add(p.resolve())
                elif p.suffix in ('.json','.tcl','.txt') and p.stat().st_size<4000000:
                    try:
                        text=p.read_text(errors='replace')
                        if p.suffix=='.json':walk_json(json.loads(text))
                        for match in re.findall(r'/[^\s{}\[\]"\';]+(?:\.db|\.tf|\.tluplus|\.map|\.ndm)',text):add(match)
                    except (ValueError,OSError):pass
    return sorted(found)


def snapshot(cache,targets):
    cache.mkdir(parents=True,exist_ok=False)
    records=[]
    for index,source in enumerate(discover(targets)):
        dest=cache/'libraries'/('{:04d}_'.format(index)+source.name)
        dest.parent.mkdir(exist_ok=True)
        if source.is_dir():
            # A symlink into a retired run would invalidate a copied NDM.
            for p in source.rglob('*'):
                if p.is_symlink():raise RuntimeError('Reference NDM contains symlink; inspect before deleting: '+str(p))
            shutil.copytree(str(source),str(dest))
            files=[p for p in source.rglob('*') if p.is_file()]
            if not files:raise RuntimeError('Empty reference library '+str(source))
            hashes={p.relative_to(source).as_posix():sha(p) for p in files}
            if any(sha(dest/n)!=h for n,h in hashes.items()):raise RuntimeError('Reference copy mismatch')
            records.append({'source':str(source),'cached':str(dest),'kind':'ndm','files_sha256':hashes})
        else:
            shutil.copy2(str(source),str(dest))
            h=sha(source)
            if sha(dest)!=h:raise RuntimeError('PDK copy mismatch')
            records.append({'source':str(source),'cached':str(dest),'kind':source.suffix,'sha256':h})
    kinds=[r['kind'] for r in records]
    # The exact new macro list will be checked after the frontend arrives.
    # Preserve old known standard/private/shared physical libraries now.
    if kinds.count('ndm')<3 or kinds.count('.db')<2 or '.tf' not in kinds or '.tluplus' not in kinds or '.map' not in kinds:
        dump(cache/'Cache.json',{'status':'INCOMPLETE_NO_DELETION_ALLOWED','libraries':records})
        raise RuntimeError('Cache incomplete: need std/private/shared NDM, std/SRAM DB, TF, TLU+, RC map. Old runs retained.')
    dump(cache/'Cache.json',{'status':'COPIED_FILE_VERIFIED_NATIVE_REOPEN_NOT_RUN','libraries':records})
    return records


def make_plan(cache):
    soc,targets=roots_and_targets()
    if any(under(cache,t) or under(SELF,t) for t in targets):raise RuntimeError('Cache/tool would be deleted')
    busy=active(targets)
    if busy:raise RuntimeError('Close old GUI/shell/jobs first; active targets: '+json.dumps(busy))
    records=snapshot(cache,targets)
    plan={'created':time.strftime('%Y-%m-%dT%H:%M:%S'),'uid':os.getuid(),'soc':str(soc),'cache':str(cache),
          'cache_manifest_sha256':sha(cache/'Cache.json'),'targets':[],
          'scope':'all previous own soc contents and own /tmp/tpusoc_* /tmp/kwt_*; new toolkit retained'}
    for t in targets:
        st=t.stat();plan['targets'].append({'path':str(t),'device':st.st_dev,'inode':st.st_ino})
    dump(cache/'CleanupPlan.json',plan)
    print('CLEANUP_PLAN_READY',cache/'CleanupPlan.json')
    for t in targets:print('RETIRE',t)
    print('PDK_CACHE',cache,'libraries='+str(len(records)))
    print('No deletion yet; native reopen must be checked before --apply.')


def apply(plan_path):
    plan=json.loads(plan_path.read_text());cache=Path(plan['cache']).resolve();soc=(Path.home()/'soc').resolve()
    if plan['uid']!=os.getuid() or plan['soc']!=str(soc):raise RuntimeError('Cleanup owner/root changed')
    if sha(cache/'Cache.json')!=plan['cache_manifest_sha256']:raise RuntimeError('Cache ledger changed')
    reopen=cache/'NativeCacheReady.txt'
    if not reopen.is_file() or reopen.read_text().strip()!='NATIVE_PDK_CACHE_READY':
        raise RuntimeError('Run probe_cache.tcl with copied reference libraries before deleting old runs')
    inventory=json.loads((cache/'Cache.json').read_text())
    for record in inventory['libraries']:
        p=Path(record['cached'])
        if record['kind']=='ndm':
            for n,h in record['files_sha256'].items():
                if sha(p/n)!=h:raise RuntimeError('Cached NDM changed')
        elif sha(p)!=record['sha256']:raise RuntimeError('Cached PDK input changed')
    targets=[]
    for record in plan['targets']:
        p=Path(record['path'])
        if p.is_symlink() or p.resolve()!=p or (p.parent!=soc and not (p.parent==Path('/tmp') and p.name.startswith(('tpusoc_','kwt_')))):
            raise RuntimeError('Unsafe deletion target '+str(p))
        if under(cache,p) or under(SELF,p):raise RuntimeError('Protected dependency inside deletion target')
        st=p.stat()
        if st.st_uid!=os.getuid() or (st.st_dev,st.st_ino)!=(record['device'],record['inode']):raise RuntimeError('Target replaced '+str(p))
        targets.append(p)
    busy=active(targets)
    if busy:raise RuntimeError('Target in use; nothing deleted: '+json.dumps(busy))
    removed=[]
    for p in targets:
        print('DELETE',p,flush=True)
        if p.is_dir():shutil.rmtree(str(p))
        else:p.unlink()
        removed.append(str(p));dump(cache/'Removed.json',{'removed':removed})
    print('CLEANUP_COMPLETE','removed='+str(len(removed)),'PDK_CACHE='+str(cache))
    subprocess.call(['df','-h',str(Path.home()),'/tmp'])
    subprocess.call(['df','-i',str(Path.home()),'/tmp'])


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command')
    a=s.add_parser('plan');a.add_argument('--cache',type=Path,default=Path('/tmp')/('chipdesign_pdk_cache_'+str(os.getuid())))
    a=s.add_parser('apply');a.add_argument('--plan',type=Path,required=True)
    a=p.parse_args()
    if a.command=='plan':make_plan(a.cache.resolve())
    elif a.command=='apply':apply(a.plan.resolve())
    else:p.error('Choose plan or apply')


if __name__=='__main__':main()
