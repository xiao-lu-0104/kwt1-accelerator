#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
bundle="$root/workspace/Server/tpusoc_shared_20261105_v1"
out="$root/workspace/Checks/BootGprFix_20261107_v1"
[[ ! -e "$out" ]] || { echo "ERROR: versioned build already exists: $out"; exit 2; }
mkdir -p "$out/original" "$out/fixed/Sw" "$out/fixed/BuildEvidence"
export PATH="$root/workspace/HostTools:$PATH"
for source in SharedMain.c Encoder.c Encoder.h Tpu.h; do
    cp "$bundle/Sw/$source" "$out/fixed/Sw/$source"
done
cp "$root/Sw/SharedStart.S" "$out/fixed/Sw/SharedStart.S"
cp "$bundle/BuildEvidence/Shared.ld" "$bundle/BuildEvidence/SharedLayout.h" "$out/fixed/BuildEvidence/"
for mode in original fixed; do
    sw="$bundle/Sw"; layout="$bundle/BuildEvidence"; dest="$out/original"
    if [[ "$mode" == fixed ]]; then sw="$out/fixed/Sw"; layout="$out/fixed/BuildEvidence"; dest="$layout"; fi
    riscv64-unknown-elf-gcc -march=rv32imac_zicsr -mabi=ilp32 -O2 -Wall -Wextra -Werror \
        -ffreestanding -fno-builtin -msmall-data-limit=0 -nostdlib -I"$layout" -Wl,--build-id=none \
        -Wl,-T,"$layout/Shared.ld" -Wl,-Map,"$dest/Shared.map" \
        "$sw/SharedStart.S" "$sw/SharedMain.c" "$sw/Encoder.c" -o "$dest/Shared.elf"
    riscv64-unknown-elf-objcopy -O binary "$dest/Shared.elf" "$dest/Shared.bin"
    riscv64-unknown-elf-objdump -d "$dest/Shared.elf" > "$dest/Shared.disasm.txt"
    python3 "$root/Server/Shared/FirmwareHex.py" "$dest/Shared.bin" "$dest/Firmware.hex"
done
cmp "$out/original/Shared.bin" "$bundle/Firmware.bin"
cmp "$out/original/Firmware.hex" "$bundle/Firmware.hex"
python3 "$here/BootFirmware.py" "$out" --bundle "$bundle"
riscv64-unknown-elf-gcc --version > "$out/fixed/BuildEvidence/Compiler.txt"
echo "PASS BOOT_FIRMWARE_BUILD: original image reproduced byte for byte; new boot executes 31 register clears; output=$out/fixed"
