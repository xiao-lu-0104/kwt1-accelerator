"""Create a small inbound-only current task/SAIF/power pipeline with no vendor data."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    firmware=ROOT/'workspace/Checks/NewPowerFirmware_20261109_v1'
    proof=json.loads((firmware/'BuildEvidence/FirmwareEvidence.json').read_text())
    for name,digest in proof['sha256'].items():
        if hashlib.sha256((firmware/'BuildEvidence'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Firmware evidence mismatch: '+name)
    files={}
    for name in ('Tasks.py','Guards.py','Power.py','Power.tcl','Run.py'):
        files['tools/'+name]=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
    for folder,names in [('RefreshDc',['Review.py']),('SharedAsic',['PrepareInventory.py','ReadProbe.py','TaskActivity.sv']),
        ('SystemBackend',['SystemTasks.py','Prepare.py','StageWatch.py','TcmInitializer.sv','AreaBreakdown.tcl','PowerCoverage.py']),
        ('Backend',['AsicCommon.tcl'])]:
        for name in names:files['tools/'+name]=(ROOT/'Server'/folder/name).read_bytes().replace(b'\r\n',b'\n')
    for path in firmware.rglob('*'):
        if path.is_file():files['firmware/'+path.relative_to(firmware).as_posix()]=path.read_bytes()
    files['PACKAGE.sha256']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mtime=1704067200
            archive.addfile(info,io.BytesIO(data))
    data=buffer.getvalue()
    entry='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_current_power_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'TPUSOC_CURRENT_POWER_PAYLOAD'
'''+base64.encodebytes(data).decode()+'''TPUSOC_CURRENT_POWER_PAYLOAD
echo "'''+hashlib.sha256(data).hexdigest()+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "CURRENT_POWER_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
echo 'SCOPE: fresh gate accelerator and new block-FF1 firmware, original CPU RTL and 120 physical SRAM models; no old SAIF reuse'
echo 'LIMITS: preparation 5min, VCS 15min, FF1 20min, encoder 45min, power each 15min; caps are not estimates'
python3 -u "$work/tools/Run.py" "$work"
'''
    output=ROOT/'workspace/Server/tpusoc_current_power_20261109_v1.sh'
    if output.exists():raise ValueError('Refusing to replace a versioned artifact')
    output.write_bytes(entry.encode())
    print('ARTIFACT',output)
    print('BYTES',output.stat().st_size)
    print('SHA256',hashlib.sha256(output.read_bytes()).hexdigest())


if __name__=='__main__':main()
