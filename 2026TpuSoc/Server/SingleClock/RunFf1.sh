#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"
out=workspace/Checks/Ff1Soc20261104
mkdir -p "$out"
export PATH="$root/workspace/HostTools:$PATH"
python=Model/.venv/bin/python
"$python" Model/MakeFf1Vectors.py
python3 Server/SingleClock/MakeLocalTest.py
riscv64-unknown-elf-gcc -march=rv32imac_zicsr -mabi=ilp32 -O2 -Wall -Wextra -Werror \
    -ffreestanding -fno-builtin -msmall-data-limit=0 -nostdlib -Wl,--build-id=none \
    -Wl,-T,Sw/Link.ld -Wl,-Map,"$out/Ff1.map" Sw/Start.S Sw/Ff1Main.c Sw/Encoder.c -o "$out/Ff1.elf"
riscv64-unknown-elf-objcopy -O binary "$out/Ff1.elf" "$out/Ff1.bin"
mapfile -t sources < <(tr -d '\r' < Backend/Files.f)
verilator --cc --exe --assert --no-timing --build -j 4 \
    -Wall -Wno-UNUSEDPARAM -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY -Wno-DECLFILENAME -Wno-TIMESCALEMOD \
    --top-module E203TpuBackend --Mdir "$out/build" \
    +define+TPU_SRAM_MODEL Sim/E203.vlt Server/Backend/LocalReset.vlt Server/SingleClock/Local.vlt \
    "${sources[@]}" Server/Backend/SpFoundry.sv Server/Backend/LocalRamspFixture.sv \
    "$root/workspace/Checks/SingleClock20261102/SocTest.cpp" \
    -CFLAGS "-std=c++17 -O2 -I$root/Sim"
for name in normal zero extreme Layer{0..11}; do
    "$out/build/VE203TpuBackend" "$out/Ff1.bin" "workspace/Sim/out/Ff1/$name" 1 ff1 > "$out/$name.log"
    tail -n 6 "$out/$name.log"
done
echo 'PASS FF1_SOC: 15 cases, real E203, shared clock, local macro fixture and AXI model; official platform pending'
