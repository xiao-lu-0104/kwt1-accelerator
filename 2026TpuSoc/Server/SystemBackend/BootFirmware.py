"""Validate executable boot initialization and record reproducible firmware evidence."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_code(binary):
    # RV32I ADDI xN,x0,0, exactly once for every writable GPR at reset entry.
    expected=b''.join(((reg<<7)|0x13).to_bytes(4,'little') for reg in range(1,32))
    if binary[:len(expected)]!=expected:
        raise ValueError('Reset entry does not execute all 31 GPR clear instructions')


def finish(out,bundle):
    original=out/'original'; fixed=out/'fixed'; evidence=fixed/'BuildEvidence'
    if (original/'Shared.bin').read_bytes()!=(bundle/'Firmware.bin').read_bytes():
        raise ValueError('Original frozen firmware not reproduced')
    if (original/'Firmware.hex').read_bytes()!=(bundle/'Firmware.hex').read_bytes():
        raise ValueError('Original full ITCM image not reproduced')
    validate_code((evidence/'Shared.bin').read_bytes())
    source=(fixed/'Sw/SharedStart.S').read_text()
    original_source=(bundle/'Sw/SharedStart.S').read_text()
    marker='    .option push\n    .option norelax\n'
    if source[source.index(marker):]!=original_source[original_source.index(marker):]:
        raise ValueError('Boot code after initialization changed')
    for name in ('SharedMain.c','Encoder.c','Encoder.h','Tpu.h'):
        if (fixed/'Sw'/name).read_bytes()!=(bundle/'Sw'/name).read_bytes():
            raise ValueError('Task driver changed: '+name)
    for name in ('Shared.ld','SharedLayout.h'):
        if (evidence/name).read_bytes()!=(bundle/'BuildEvidence'/name).read_bytes():
            raise ValueError('Memory layout changed: '+name)
    words=(evidence/'Firmware.hex').read_text().split()
    image=b''.join(int(word,16).to_bytes(8,'little') for word in words)
    code=(evidence/'Shared.bin').read_bytes()
    if len(words)!=32768 or image!=code+bytes(262144-len(code)):
        raise ValueError('Full ITCM image does not match fixed executable')
    record={'change':'Execute ADDI x1..x31,x0,0 at reset entry before original boot/C startup',
        'original_firmware_rebuilt_byte_identical':True,'gpr_clear_instructions':31,
        'original_hex_sha256':sha(bundle/'Firmware.hex'),'original_bin_sha256':sha(bundle/'Firmware.bin'),
        'fixed_hex_sha256':sha(evidence/'Firmware.hex'),'fixed_bin_sha256':sha(evidence/'Shared.bin'),
        'original_inputs':{str(p.relative_to(bundle)):sha(p) for p in
            [bundle/'Sw'/n for n in ('SharedStart.S','SharedMain.c','Encoder.c','Encoder.h','Tpu.h')]+
            [bundle/'BuildEvidence'/n for n in ('Shared.ld','SharedLayout.h')]},
        'scope':'Firmware startup only; CPU/accelerator RTL, macro wrappers, driver algorithms and memory layout unchanged',
        'server_validation':'PENDING_FF1_AND_ENCODER_WITH_STRICT_GUARDS; no system power acceptance'}
    (evidence/'BootFix.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path); parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args(); finish(args.out,args.bundle)
