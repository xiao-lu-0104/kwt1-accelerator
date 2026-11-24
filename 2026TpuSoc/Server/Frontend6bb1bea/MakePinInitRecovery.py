"""Small reversible repair: physical memory pin init/readback; reuse system DC."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import textwrap
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'release/newpower_6bb1bea'

def main():
    prior_archive=OUT/'payload.before_pin_init_repair.tar.gz'
    if not prior_archive.exists():shutil.copy2(OUT/'payload.tar.gz',prior_archive)
    with tarfile.open(prior_archive) as archive:
        prior={name:archive.extractfile(name).read() for name in ['tools/RunPower.py','tools/PowerTest.sv']}
    new={name:(HERE/Path(name).name).read_bytes().replace(b'\r\n',b'\n') for name in prior}
    digest=lambda b:hashlib.sha256(b).hexdigest()
    package={'before':{n:digest(b) for n,b in prior.items()},'after':{n:digest(b) for n,b in new.items()},
             'data':{n:base64.b64encode(b).decode() for n,b in new.items()}}
    packed=gzip.compress(json.dumps(package).encode())
    body='''#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PIN_INIT_REPAIR'
from pathlib import Path
import base64,gzip,hashlib,json,os,re,time
root=Path('/tmp/final_power_6bb1bea_'+str(os.getuid()))
assert not root.is_symlink() and root.resolve()==root, 'Unexpected power directory'
def digest(data):return hashlib.sha256(data).hexdigest()
package=json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))
manifest_path=root/'PowerManifest.json'
manifest=json.loads(manifest_path.read_text())
assert manifest['source_commit']=='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6','Wrong power source'
for name,expected in manifest['files_sha256'].items():
    p=(root/name).resolve()
    assert root in p.parents and digest(p.read_bytes())==expected,'Changed original input: '+name
system=root/'system'
complete=json.loads((system/'Complete.json').read_text())
assert complete['source_commit']==manifest['source_commit'],'Wrong system candidate'
candidate=system/'candidate.v'
before_netlist=digest(candidate.read_bytes())
assert before_netlist==complete['netlist_sha256'],'System netlist changed'
current={n:digest((root/n).read_bytes()) for n in package['after']}
if current==package['after']:
    print('PIN_INIT_REPAIR_ALREADY_APPLIED; any new failed attempt remains untouched')
else:
    assert current==package['before'],'Unexpected runner/testbench version; no patch applied'
    # Do not move a stage still used by a running process.
    targets=[root/'ff1',root/'encoder']
    if Path('/proc').is_dir():
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
            try:
                if proc.stat().st_uid!=os.getuid():continue
                cwd=(proc/'cwd').resolve()
                cmd=(proc/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')
                assert not any(cwd==p or p in cwd.parents or str(p) in cmd for p in targets),'Task stage still used by PID '+proc.name
            except OSError:pass
    stamp=time.strftime('%Y%m%d_%H%M%S')
    backup=root/('pin_init_repair_inputs_'+stamp);backup.mkdir(exist_ok=False)
    (backup/'PowerManifest.json').write_bytes(manifest_path.read_bytes())
    for n in package['before']:(backup/Path(n).name).write_bytes((root/n).read_bytes())
    moved={}
    for old in targets:
        if not old.exists():continue
        assert not old.is_symlink() and old.resolve().parent==root and old.stat().st_uid==os.getuid(),'Unsafe stage path'
        assert not (old/'Activity.json').exists(),'A validated activity stage exists; inspect before replacing it'
        target=root/(old.name+'_failed_before_pin_init_'+stamp)
        assert not target.exists(),'Backup path collision'
        old.rename(target);moved[str(old)]=str(target)
    for n,encoded in package['data'].items():
        data=base64.b64decode(encoded)
        assert digest(data)==package['after'][n],'Repair payload damaged'
        (root/n).write_bytes(data)
        manifest['files_sha256'][n]=package['after'][n]
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\\n')
    record={'repair':'physical SRAM pin zero/write/readback plus real ITCM masked-write firmware initialization; no task-time forces',
            'before_files':current,'after_files':package['after'],'moved_failed_stages':moved,
            'unchanged_system_netlist_sha256':before_netlist,'source_commit':manifest['source_commit']}
    (root/'PinInitRecovery.json').write_text(json.dumps(record,indent=2)+'\\n')
    print('PHYSICAL_MEMORY_INIT_RECOVERY_READY')
assert digest(candidate.read_bytes())==before_netlist,'Unexpected netlist mutation'
print('REUSING_SYSTEM_DDC_NO_RESYNTHESIS')
PIN_INIT_REPAIR
root="/tmp/final_power_6bb1bea_$(id -u)"
exec > >(tee -a "$root/runner.log") 2>&1
python3 -u "$root/tools/RunPower.py" "$root"
'''.replace('PAYLOAD',repr(base64.b64encode(packed).decode()))
    (OUT/'ResumePowerPinInit_6bb1bea.sh').write_text(body,encoding='utf-8',newline='\n')
    (OUT/'PinInitRepairBuild.json').write_text(json.dumps({'before':package['before'],'after':package['after'],'script_chars':len(body)},indent=2)+'\n')
    print((OUT/'PinInitRepairBuild.json').read_text())

if __name__=='__main__':main()
