#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
out="$root/workspace/Checks/NewPowerFirmware_20261109_v1"
export PATH="$root/workspace/HostTools:$PATH"
sw="$out/Sw"; dest="$out/BuildEvidence"
[[ ! -e "$dest/Shared.elf" ]]
riscv64-unknown-elf-gcc -march=rv32imac_zicsr -mabi=ilp32 -O2 -Wall -Wextra -Werror \
    -ffreestanding -fno-builtin -msmall-data-limit=0 -nostdlib -I"$dest" -Wl,--build-id=none \
    -Wl,-T,"$dest/Shared.ld" -Wl,-Map,"$dest/Shared.map" \
    "$sw/SharedStart.S" "$sw/SharedMain.c" "$sw/Encoder.c" -o "$dest/Shared.elf"
riscv64-unknown-elf-objcopy -O binary "$dest/Shared.elf" "$dest/Shared.bin"
riscv64-unknown-elf-objdump -d "$dest/Shared.elf" > "$dest/Shared.disasm.txt"
python3 "$root/Server/Shared/FirmwareHex.py" "$dest/Shared.bin" "$dest/Firmware.hex"
python3 - "$dest" <<'CHECK_NEW_POWER_BOOT'
from pathlib import Path
import hashlib,json,sys
p=Path(sys.argv[1]); code=(p/'Shared.bin').read_bytes()
expected=b''.join(((reg<<7)|0x13).to_bytes(4,'little') for reg in range(1,32))
assert code.startswith(expected),'Missing 31 boot GPR clear instructions'
words=(p/'Firmware.hex').read_text().split()
assert len(words)==32768
image=b''.join(int(w,16).to_bytes(8,'little') for w in words)
assert image==code+bytes(262144-len(code))
record={'frontend_revision':'c03eb048481b7d271dba54e518092c2eb9aa528f','boot_gpr_clears':31,
 'FF1_blocks':[32,32,32,3], 'functional_status':'PENDING_CURRENT_GATE_TASKS',
 'sha256':{q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in p.iterdir() if q.is_file()}}
(p/'FirmwareEvidence.json').write_text(json.dumps(record,indent=2)+'\n')
print('NEW_FIRMWARE_BUILD_PASS: upstream current driver; block FF1; full 256KiB ITCM image; 31 boot GPR clears')
CHECK_NEW_POWER_BOOT
