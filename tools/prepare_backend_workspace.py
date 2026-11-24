"""Create a disposable replay workspace with external frontend dependencies.

This never pushes a repository or vendors teammate/frontend source into this repo.
"""
import argparse
from pathlib import Path
import shutil
import subprocess

REPOSITORY=Path(__file__).resolve().parents[1]
UPSTREAM='https://github.com/kkk73/2026TpuSoc.git'
REVISION='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6'
SNAPSHOTS={
 '2026TpuSoc_frontend_20261109':'c03eb048481b7d271dba54e518092c2eb9aa528f',
 '2026TpuSoc_frontend_20261110_707cd7f':'707cd7f4a0a4d416d11bac71112980079e0a9d34',
 '2026TpuSoc_frontend_20261112_fa5f062':'fa5f06250d2ca2da5041c78fa745707e11549194',
 '2026TpuSoc_frontend_20261113_7cf5155':'7cf51551563f6b431cd59ac99e320d2e74c9fd77',
 '2026TpuSoc_frontend_20261113_6bb1bea':REVISION,
}

def run(*args):
    subprocess.run(args,check=True)

def prepare(destination,revision=REVISION,all_revisions=False,submodules=False,frontend_source=UPSTREAM):
    destination=destination.resolve()
    if destination.exists():raise ValueError('Choose a new empty destination: '+str(destination))
    if destination==REPOSITORY or REPOSITORY in destination.parents and not destination.is_relative_to(REPOSITORY/'workspace'):
        raise ValueError('Inside this repository use workspace/; external empty paths are also supported')
    destination.mkdir(parents=True)
    frontend=destination/'2026TpuSoc'
    run('git','clone','--no-checkout',frontend_source,str(frontend))
    run('git','-C',str(frontend),'remote','set-url','--push','origin','DISABLED_READ_ONLY_DEPENDENCY')
    run('git','-C',str(frontend),'checkout','--detach',revision)
    if submodules:run('git','-C',str(frontend),'submodule','update','--init','--recursive')
    snapshots=SNAPSHOTS if all_revisions else {'2026TpuSoc_frontend_20261113_6bb1bea':REVISION}
    for name,rev in snapshots.items():
        run('git','-C',str(frontend),'worktree','add','--detach',str(destination/name),rev)
    # Only overlay contributions tracked in the personal repository.
    result=subprocess.check_output(['git','-C',str(REPOSITORY),'ls-files','-z'])
    for name in result.decode().split('\0'):
        if not name:continue
        if name.startswith(('2026TpuSoc/','release/')):
            source=REPOSITORY/name;target=destination/name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    print('BACKEND_WORKSPACE='+str(destination))
    print('FRONTEND_IS_EXTERNAL='+UPSTREAM)
    print('FRONTEND_PUSH_DISABLED=1')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,default=REPOSITORY/'workspace/replay')
    parser.add_argument('--revision',default=REVISION)
    parser.add_argument('--all-revisions',action='store_true')
    parser.add_argument('--init-submodules',action='store_true')
    parser.add_argument('--frontend-source',default=UPSTREAM,help='Read-only external URL or local Git mirror')
    args=parser.parse_args()
    prepare(args.destination,args.revision,args.all_revisions,args.init_submodules,args.frontend_source)

if __name__=='__main__':main()
