import base64,gzip,hashlib,json
from pathlib import Path
root=Path('E:/chipdesign')
here=root/'2026TpuSoc/Server/Frontend6bb1bea'
out=root/'release/newpower_6bb1bea'
runner=(here/'RunPower.py').read_text()
before=hashlib.sha256((here/'RunPower.py').read_bytes().replace(b'\r\n',b'\n')).hexdigest()
needle="    (directory/'MemoryInit.sv').write_text('\\n'.join(lines)+'\\n')"
assert runner.count(needle)==1
runner=runner.replace(needle,needle+'\n    from BinaryStartup import generate\n    generate(root,directory,cells)')
needle2="        if not (directory/'Activity.json').is_file():"
assert runner.count(needle2)==1
qualification='''        if task=='ff1' and not (directory/'StartupQualified.json').is_file():
            for pattern in (0,1,2):
                comparison=directory/('startup_pattern_'+str(pattern));comparison.mkdir(exist_ok=False)
                native([str(directory/'simv'),'+TASK=ff1','+SOURCE='+str(directory/'source.hex'),'+EXPECTED='+str(directory/'expected.hex'),
                    '+SAIF='+str(comparison/'unused.saif'),'+INIT_PATTERN='+str(pattern),'+STARTUP_CHECK_ONLY'],comparison,'BINARY_STARTUP_SHORT_PASS pattern='+str(pattern))
                print('STARTUP_PATTERN_PASS pattern='+str(pattern),flush=True)
            save(directory/'StartupQualified.json',{'patterns':[0,1,2],'scope':'reset plus initial copy transactions only; full cold task still required'})
'''
runner=runner.replace(needle2,qualification+needle2)
runner=runner.replace("'native_saif':coverage}","'native_saif':coverage,'startup_policy':'fixed-random binary accelerator FF initialization; released after first reset clock; no task-time force'}")
runner=runner.replace("'tasks':summaries,'system':current,", "'tasks':summaries,'system':current,'startup_policy':'fixed-random binary accelerator FF initialization; released after first reset clock; not all-X natural-reset verification',")
payload={'before':before,'files':{'tools/RunPower.py':base64.b64encode(runner.encode()).decode(),
    'tools/BinaryStartup.py':base64.b64encode((here/'BinaryStartup.py').read_bytes().replace(b'\r\n',b'\n')).decode()}}
encoded=base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
script='''#!/usr/bin/env bash
set -euo pipefail
python3 - <<'REPAIR'
from pathlib import Path
import base64,gzip,hashlib,json,os,time
root=Path('/tmp/final_power_6bb1bea_'+str(os.getuid()))
assert root.resolve()==root and not root.is_symlink()
p=json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))
digest=lambda b:hashlib.sha256(b).hexdigest()
manifest_path=root/'PowerManifest.json'
manifest=json.loads(manifest_path.read_text())
assert manifest['source_commit']=='6bb1bea04c4dbf9456a8362be237ad68a8f7bfd6'
for n,h in manifest['files_sha256'].items():assert digest((root/n).read_bytes())==h,'Changed input '+n
candidate=root/'system/candidate.v'
net_sha=digest(candidate.read_bytes())
assert net_sha==json.loads((root/'system/Complete.json').read_text())['netlist_sha256']
assert digest((root/'tools/RunPower.py').read_bytes())==p['before'],'Runner version differs; not modified'
targets=[root/'ff1',root/'encoder']
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
    try:
        if proc.stat().st_uid!=os.getuid():continue
        cwd=(proc/'cwd').resolve();cmd=(proc/'cmdline').read_bytes().decode(errors='replace')
        assert not any(cwd==x or x in cwd.parents or str(x) in cmd for x in targets),'Running task PID '+proc.name
    except OSError:pass
stamp=time.strftime('%Y%m%d_%H%M%S')
backup=root/('binary_startup_inputs_'+stamp);backup.mkdir()
(backup/'PowerManifest.json').write_bytes(manifest_path.read_bytes())
(backup/'RunPower.py').write_bytes((root/'tools/RunPower.py').read_bytes())
for old in targets:
    if old.exists():
        assert old.resolve().parent==root and not old.is_symlink() and old.stat().st_uid==os.getuid()
        assert not (old/'Activity.json').exists(),'Validated activity exists; leave unchanged'
        old.rename(root/(old.name+'_failed_before_binary_'+stamp))
for n,encoded in p['files'].items():
    data=base64.b64decode(encoded);(root/n).write_bytes(data);manifest['files_sha256'][n]=digest(data)
manifest_path.write_text(json.dumps(manifest,indent=2)+'\\n')
(root/'BinaryStartupRecovery.json').write_text(json.dumps({'policy':'explicit binary accelerator FF startup; one reset clock only; default fixed random; no task-time forcing','system_netlist_sha256':net_sha,'backup':str(backup)},indent=2)+'\\n')
assert digest(candidate.read_bytes())==net_sha
print('BINARY_STARTUP_RECOVERY_READY; SYSTEM_DDC_REUSED; ASSERTIONS_UNCHANGED',flush=True)
REPAIR
task_root="/tmp/final_power_6bb1bea_$(id -u)"
exec > >(tee -a "$task_root/runner.log") 2>&1
python3 -u "$task_root/tools/RunPower.py" "$task_root"
'''.replace('PAYLOAD',repr(encoded))
(out/'ResumePowerBinary_6bb1bea.sh').write_text(script,encoding='utf-8',newline='\n')
(out/'RunPower.binary_startup.py').write_text(runner,encoding='utf-8',newline='\n')
(out/'CopyBinaryRecoveryToClipboard.ps1').write_text("$ErrorActionPreference='Stop'\nSet-Clipboard -Value ([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'ResumePowerBinary_6bb1bea.sh'),[Text.Encoding]::UTF8))\nWrite-Host 'COPIED: ResumePowerBinary_6bb1bea.sh'\n",encoding='utf-8')
print('SCRIPT_CHARS',len(script),'BEFORE',before)
