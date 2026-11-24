#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
out="$root/workspace/Checks/PowerFirmware_20261110_707cd7f_v1"
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
python3 - "$out" <<'VERIFY_707CD7F_FIRMWARE'
from pathlib import Path
import hashlib,json,sys
out=Path(sys.argv[1]); p=out/'BuildEvidence'; code=(p/'Shared.bin').read_bytes()
expected=b''.join(((reg<<7)|0x13).to_bytes(4,'little') for reg in range(1,32))
assert code.startswith(expected),'Missing boot GPR clear instructions'
words=(p/'Firmware.hex').read_text().split()
assert len(words)==32768
image=b''.join(int(w,16).to_bytes(8,'little') for w in words)
assert image==code+bytes(262144-len(code))
assert 'const uint32_t Blocks[4] = {32, 32, 28, 7};' in (out/'Sw/Encoder.c').read_text()
assert 'TpuRunFf1Tasks(&Ff1, 1, TPU_OUTPUT, 50688, &Mail[1])' in (out/'Sw/SharedMain.c').read_text()
record={'frontend_revision':'707cd7f4a0a4d416d11bac71112980079e0a9d34','boot_gpr_clears':31,
 'FF1_blocks':[32,32,28,7],'FF1_task_count':1,'functional_status':'PENDING_CURRENT_SYSTEM_GATE_TASKS',
 'scope':'one FF1 normal and one layer encoder power tasks; not a 12-task throughput reproduction',
 'sha256':{q.relative_to(out).as_posix():hashlib.sha256(q.read_bytes()).hexdigest() for q in out.rglob('*') if q.is_file()}}
(p/'FirmwareEvidence.json').write_text(json.dumps(record,indent=2)+'\n')
print('NEW_707CD7F_FIRMWARE_BUILD_PASS: exact driver, 32+32+28+7 blocks, full ITCM image, 31 boot GPR clears; runtime tasks pending')
VERIFY_707CD7F_FIRMWARE
