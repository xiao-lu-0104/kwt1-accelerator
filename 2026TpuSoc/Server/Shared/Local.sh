#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"
mkdir -p workspace/SharedRuns
if [[ $# == 2 && "$1" == --resume ]]; then
    work=$(cd "$2" && pwd -P)
    [[ "$work" == "$root/workspace/SharedRuns/"* && -f "$work/Scope.json" ]] || exit 2
    python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["scope"] == "LOCAL_UPSTREAM_WIDTH_COMPARISON"' "$work/Scope.json"
elif [[ $# == 0 ]]; then
    work=$(mktemp -d "$root/workspace/SharedRuns/local_20261105_XXXXXX")
else
    echo 'Usage: Local.sh [--resume workspace/SharedRuns/<local run>]'; exit 2
fi
echo "SHARED_WORK: $work"
export PATH="$root/workspace/HostTools:$PATH"
python=Model/.venv/bin/python
if [[ ! -f "$work/Scope.json" ]]; then
    "$python" Model/MakeFf1Vectors.py
    "$python" Model/MakeSharedVectors.py
    python3 Server/Shared/Prepare.py --platform e203_hbirdv2 --out "$work" --local-widths
fi
riscv64-unknown-elf-gcc -march=rv32imac_zicsr -mabi=ilp32 -O2 -Wall -Wextra -Werror \
    -ffreestanding -fno-builtin -msmall-data-limit=0 -nostdlib -I"$work" -Wl,--build-id=none \
    -Wl,-T,"$work/Shared.ld" -Wl,-Map,"$work/Shared.map" \
    Sw/SharedStart.S Sw/SharedMain.c Sw/Encoder.c -o "$work/Shared.elf"
riscv64-unknown-elf-objcopy -O binary "$work/Shared.elf" "$work/Shared.bin"
python3 Server/Shared/FirmwareHex.py "$work/Shared.bin" "$work/Firmware.hex"
if [[ -f "$work/SourceInputs.json" ]]; then
    python3 Server/Shared/Snapshot.py "$work" --verify
else
    python3 Server/Shared/Snapshot.py "$work"
fi
verilator --binary --timing --assert --build -j 4 --top-module SharedTest \
    -Wall -Wno-UNUSEDPARAM -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY \
    -Wno-TIMESCALEMOD -Wno-DECLFILENAME -DFPGA_SOURCE -DFPGA \
    Sim/E203.vlt Server/Shared/Local.vlt -f "$work/Files.f" --Mdir "$work/build"
for mode in ff1 one twelve; do
    kind=0; layers=1; vectors="$root/workspace/Sim/out/Shared"
    if [[ "$mode" == ff1 ]]; then kind=1; vectors="$vectors/Ff1_Layer0"; fi
    if [[ "$mode" == twelve ]]; then layers=12; fi
    "$work/build/VSharedTest" +FIRMWARE="$work/Firmware.hex" +VECTORS="$vectors" \
        +KIND="$kind" +LAYERS="$layers" > "$work/$mode.log"
    tail -n 4 "$work/$mode.log"
done
python3 Server/Shared/Snapshot.py "$work" --verify
echo "PASS SHARED_LOCAL: original CPU/LSU/TCM RTL, copied widths=18; competition server pending; $work"
