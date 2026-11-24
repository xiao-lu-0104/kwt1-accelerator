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
    prior_archive=OUT/'payload.before_guard_repair.tar.gz'
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
python3 - <<'GUARD_REPAIR'
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
    print('GUARD_REPAIR_ALREADY_APPLIED; any new failed attempt remains untouched')
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
    backup=root/('guard_repair_inputs_'+stamp);backup.mkdir(exist_ok=False)
    (backup/'PowerManifest.json').write_bytes(manifest_path.read_bytes())
    for n in package['before']:(backup/Path(n).name).write_bytes((root/n).read_bytes())
    moved={}
    for old in targets:
        if not old.exists():continue
        assert not old.is_symlink() and old.resolve().parent==root and old.stat().st_uid==os.getuid(),'Unsafe stage path'
        assert not (old/'Activity.json').exists(),'A validated activity stage exists; inspect before replacing it'
        target=root/(old.name+'_failed_before_guard_'+stamp)
        assert not target.exists(),'Backup path collision'
        old.rename(target);moved[str(old)]=str(target)
    for n,encoded in package['data'].items():
        data=base64.b64decode(encoded)
        assert digest(data)==package['after'][n],'Repair payload damaged'
        (root/n).write_bytes(data)
        manifest['files_sha256'][n]=package['after'][n]
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\\n')
    record={'repair':'read/write-specific effective-data checks; preserve address/write validation and physical pin initialization',
            'before_files':current,'after_files':package['after'],'moved_failed_stages':moved,
            'unchanged_system_netlist_sha256':before_netlist,'source_commit':manifest['source_commit']}
    (root/'GuardRecovery.json').write_text(json.dumps(record,indent=2)+'\\n')
    print('SHARED_GUARD_RECOVERY_READY')

# Validate the actual extracted assertion in the installed four-state simulator.
import ast,sys,subprocess
sys.path.insert(0,str(root/'tools'))
from NativeHelpers import native
unit=root/('guard_unit_'+time.strftime('%Y%m%d_%H%M%S'));unit.mkdir()
tb=(root/'tools/PowerTest.sv').read_text()
check=re.search(r'    task automatic CheckSharedRequest\\(.*?    endtask',tb,re.S)
assert check,'Missing reviewed guard task'
unit_source='`timescale 1ns/1ps\\nmodule GuardTest;\\ninteger CaseId;\\nTASK\\ninitial begin\\nif (!$value$plusargs("CASE=%d",CaseId)) $fatal(1,"No case");\\ncase(CaseId)\\n0: CheckSharedRequest(32\\'ha0000000,1\\'b1,4\\'bxxxx,32\\'hxxxxxxxx);\\n1: CheckSharedRequest(32\\'ha0000000,1\\'b0,4\\'bxxxx,32\\'h12345678);\\n2: CheckSharedRequest(32\\'ha0000000,1\\'b0,4\\'hf,32\\'hxxxxxxxx);\\n3: CheckSharedRequest(32\\'hxxxxxxxx,1\\'b1,4\\'hf,32\\'h0);\\n4: CheckSharedRequest(32\\'ha0000000,1\\'bx,4\\'hf,32\\'h0);\\n5: CheckSharedRequest(32\\'h0,1\\'b1,4\\'hf,32\\'h0);\\n6: CheckSharedRequest(32\\'ha0000000,1\\'b0,4\\'hf,32\\'h12345678);\\nendcase\\n$display("GUARD_UNIT_ACCEPT case=%0d",CaseId);$finish;\\nend\\nendmodule\\n'.replace('TASK',check[0])
(unit/'GuardTest.sv').write_text(unit_source)
previous=list(root.glob('ff1_failed_before_guard_*/compile/Compile.py'))
assert previous,'Original VCS command not found'
tree=ast.parse(sorted(previous)[-1].read_text())
cmds=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cmd' for t in n.targets)]
assert len(cmds)==1
cmd=[cmds[0][0],'-full64','-sverilog','-top','GuardTest',str(unit/'GuardTest.sv'),'-o',str(unit/'simv')]
helper=unit/'Compile.py'
helper.write_text('import subprocess\\nsubprocess.check_call('+repr(cmd)+')\\nprint("GUARD_UNIT_COMPILED")\\n')
native(['python3',str(helper)],unit,'GUARD_UNIT_COMPILED')
for case in range(7):
    result=subprocess.run([str(unit/'simv'),'+CASE='+str(case)],cwd=str(unit),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log=result.stdout.decode(errors='replace');(unit/('case%d.log'%case)).write_text(log)
    expected='GUARD_UNIT_ACCEPT' if case in (0,6) else 'UNKNOWN_EFFECTIVE_SHARED_WRITE' if case in (1,2) else 'INVALID_SHARED_ADDRESS_OR_CONTROL'
    assert expected in log,'Four-state assertion test failed: case '+str(case)+'\\n'+log
    print('FOUR_STATE_GUARD_TEST_PASS case='+str(case),flush=True)

assert digest(candidate.read_bytes())==before_netlist,'Unexpected netlist mutation'
print('REUSING_SYSTEM_DDC_NO_RESYNTHESIS')
GUARD_REPAIR
root="/tmp/final_power_6bb1bea_$(id -u)"
exec > >(tee -a "$root/runner.log") 2>&1
python3 -u "$root/tools/RunPower.py" "$root"
'''.replace('PAYLOAD',repr(base64.b64encode(packed).decode()))
    (OUT/'ResumePowerGuard_6bb1bea.sh').write_text(body,encoding='utf-8',newline='\n')
    (OUT/'GuardRepairBuild.json').write_text(json.dumps({'before':package['before'],'after':package['after'],'script_chars':len(body)},indent=2)+'\n')
    print((OUT/'GuardRepairBuild.json').read_text())

if __name__=='__main__':main()
