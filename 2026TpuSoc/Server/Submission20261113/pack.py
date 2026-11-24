"""Build offline prep/model/source archives locally; never fetch on EDA server."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from evaluate import sha,save,git_revision,PINNED_MODEL,load

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[2]


def git_files(repo,commit,paths):
    data=subprocess.check_output(['git','-C',str(repo),'archive',commit]+list(paths))
    result={}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for m in archive:
            if m.isfile():result[m.name]=archive.extractfile(m).read()
            elif m.issym():raise ValueError('Resolve source symlink explicitly: '+m.name)
    return result


def frozen(files,commit):
    files=dict(files)
    files['FrozenSource.json']=(json.dumps({'source_commit':commit,'files_sha256':{
        p:hashlib.sha256(b).hexdigest() for p,b in sorted(files.items())}},indent=2)+'\n').encode()
    return files


def archive(path,files):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(str(path),'w:gz') as t:
        for name,b in sorted(files.items()):
            if name.startswith('/') or '..' in Path(name).parts:raise ValueError('Unsafe archive path')
            m=tarfile.TarInfo(name);m.size=len(b);m.mode=0o755 if name.endswith('.sh') else 0o644
            m.mtime=1794528000;t.addfile(m,io.BytesIO(b))
    # Verify actual generated payload, not only the input dictionaries.
    with tarfile.open(str(path)) as t:
        actual={m.name:t.extractfile(m).read() for m in t if m.isfile()}
    if actual!=files:raise ValueError('Archive round-trip failed')
    save(str(path)+'.json',{'file_count':len(files),'bytes':path.stat().st_size,'sha256':sha(path)})
    print('OFFLINE_PACKAGE_READY',path,'bytes='+str(path.stat().st_size),'files='+str(len(files)))


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prep','bootstrap','assets','source','wheels'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--frontend',type=Path)
    p.add_argument('--config',type=Path);p.add_argument('--model',type=Path)
    p.add_argument('--cpu-repo',type=Path,help='Local existing E203 Git repository holding the new pinned gitlink')
    p.add_argument('--dataset',type=Path);p.add_argument('--samples',type=Path);p.add_argument('--wheel-dir',type=Path)
    a=p.parse_args();files={}
    if a.mode in ['prep','bootstrap']:
        for f in HERE.iterdir():
            if f.is_file() and f.suffix in ['.py','.tcl','.sv','.json','.sh','.ps1','.txt']:
                if a.mode=='bootstrap' and f.name not in ['clean_server.py','probe_cache.py','flow.py','evaluate.py','power_summary.py']:
                    continue
                files['submission_20261113/'+f.name]=f.read_bytes()
        if a.mode=='prep':
            guide=WORKSPACE/'doc/新版最终冲刺_20261113.md'
            if guide.is_file():files['submission_20261113/操作指南.md']=guide.read_bytes()
    elif a.mode=='assets':
        if git_revision(a.model)!=PINNED_MODEL:raise ValueError('Wrong model')
        model_paths=['models_data_v2_12_labels/kwt1/'+n for n in ['best_weights.index','best_weights.data-00000-of-00001','flags.json','labels.txt']]
        model_files=git_files(a.model,PINNED_MODEL,model_paths+['kws_streaming/layers','kws_streaming/__init__.py'])
        for n,b in frozen(model_files,PINNED_MODEL).items():files['evaluation_assets/official_model/'+n]=b
        sample=load(a.samples)
        files['evaluation_assets/SmokeSamples.json']=a.samples.read_bytes()
        for item in sample['samples']:
            if item.get('silence'):continue
            files['evaluation_assets/smoke_audio/'+item['path']]=(a.dataset/item['path']).read_bytes()
        files['evaluation_assets/README.txt']=b'Raw validation smoke WAVs only; not official evaluation selection. Official graders provide their own paths. No training or tuning.\n'
    elif a.mode=='source':
        config=load(a.config)
        if not config.get('frontend_bound'):raise ValueError('Bind new frontend first')
        commit=config['source_commit']
        if git_revision(a.frontend)!=commit:raise ValueError('Config/frontend mismatch')
        source=git_files(a.frontend,commit,['Rtl','Backend','Sim','Sw','Model','Server','Makefile','README.md','.gitmodules'])
        # Frozen external CPU RTL is bundled locally. No server submodule fetch.
        line=subprocess.check_output(['git','-C',str(a.frontend),'ls-tree',commit,'e203_hbirdv2'],universal_newlines=True)
        cpu_commit=line.split()[2]
        cpu=a.cpu_repo or a.frontend/'e203_hbirdv2'
        subprocess.check_call(['git','-C',str(cpu),'cat-file','-e',cpu_commit+'^{commit}'])
        for n,b in git_files(cpu,cpu_commit,['rtl']).items():source['e203_hbirdv2/'+n]=b
        for n,b in frozen(source,commit).items():files['source_'+commit[:7]+'/'+n]=b
        # config paths are server-specific, so they are distributed separately
        # after binding; never silently publish a localhost path as server-ready.
    else:
        wheels=sorted(a.wheel_dir.glob('*.whl'))
        if not wheels or not any(p.name.startswith('tensorflow_cpu-2.4.4-') for p in wheels):raise ValueError('Linux Python3.6 wheel set incomplete')
        for f in wheels:files['server_wheels_py36/'+f.name]=f.read_bytes()
        files['server_wheels_py36/requirements.txt']=b'tensorflow-cpu==2.4.4\nnumpy==1.19.5\n'
    archive(a.out,files)


if __name__=='__main__':main()
