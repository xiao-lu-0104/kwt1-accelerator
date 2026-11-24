"""Stage exact 707cd7f drivers and adapt only the shared-task entry to its new API."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FRONT = ROOT.parent / '2026TpuSoc_frontend_20261110_707cd7f'
REV = '707cd7f4a0a4d416d11bac71112980079e0a9d34'


def main():
    bundle = ROOT / 'workspace/Server/tpusoc_shared_20261105_v1'
    manifest = bundle / 'MANIFEST.sha256'
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != 'baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83':
        raise ValueError('Historical task harness manifest changed')
    ledger = dict(line.split('  ', 1)[::-1] for line in manifest.read_text().splitlines())
    out = ROOT / 'workspace/Checks/PowerFirmware_20261110_707cd7f_v1'
    out.mkdir(exist_ok=False)
    (out / 'Sw').mkdir()
    (out / 'BuildEvidence').mkdir()
    origins = {}
    for name in ('Encoder.c', 'Encoder.h', 'Tpu.h'):
        data = subprocess.check_output(['git', '-C', str(FRONT), 'show', REV + ':Sw/' + name])
        (out / 'Sw' / name).write_bytes(data)
        origins['Sw/' + name] = {'revision': REV, 'sha256': hashlib.sha256(data).hexdigest()}
    for name in ('Sw/SharedMain.c', 'BuildEvidence/Shared.ld', 'BuildEvidence/SharedLayout.h'):
        src = bundle / name
        if hashlib.sha256(src.read_bytes()).hexdigest() != ledger[name]:
            raise ValueError('Historical harness changed: ' + name)
        text = src.read_text()
        if name.endswith('SharedMain.c'):
            old = 'if (TpuRunFf1(TPU_INPUT, TPU_PARAMETERS, TPU_OUTPUT, Mail[6])) goto Failed;'
            if text.count(old) != 1:
                raise ValueError('Unexpected old FF1 entry')
            text = text.replace(old, 'TpuFf1Params Ff1 = {TPU_INPUT, TPU_PARAMETERS, Mail[6]};\n'
                '        if (TpuRunFf1Tasks(&Ff1, 1, TPU_OUTPUT, 50688, &Mail[1])) goto Failed;')
        (out / name).write_text(text, newline='\n')
        origins[name] = {'original_sha256': ledger[name], 'change': 'new one-task FF1 API; completed pointer remains mailbox word1' if name.endswith('SharedMain.c') else 'unchanged'}
    boot = ROOT / 'Sw/SharedStart.S'
    text = boot.read_text()
    if '.irp reg,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31' not in text:
        raise ValueError('Executable GPR initialization absent')
    (out / 'Sw/SharedStart.S').write_text(text, newline='\n')
    origins['Sw/SharedStart.S'] = {'sha256': hashlib.sha256(boot.read_bytes()).hexdigest(), 'purpose': '31 normal GPR clear instructions before C startup'}
    (out / 'BuildEvidence/FirmwareOrigins.json').write_text(json.dumps(origins, indent=2) + '\n')
    print(out)


if __name__ == '__main__':
    main()
