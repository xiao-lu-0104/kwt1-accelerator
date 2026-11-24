#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"
python3 Server/SingleClock/MakeLocalTest.py
mapfile -t sources < <(tr -d '\r' < Backend/Files.f)
verilator --cc --exe --assert --no-timing --build -j 4 \
    -Wall -Wno-UNUSEDPARAM -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY -Wno-DECLFILENAME -Wno-TIMESCALEMOD \
    --top-module E203TpuBackend --Mdir workspace/Checks/SingleClock20261102/build \
    +define+TPU_SRAM_MODEL Sim/E203.vlt Server/Backend/LocalReset.vlt Server/SingleClock/Local.vlt \
    "${sources[@]}" Server/Backend/SpFoundry.sv Server/Backend/LocalRamspFixture.sv \
    "$root/workspace/Checks/SingleClock20261102/SocTest.cpp" \
    -CFLAGS "-std=c++17 -O2 -I$root/Sim"
echo 'LOCAL_SCOPE: new upstream single-clock top + real-pin adapter + local macro test double; not vendor timing'
for mode in one final; do
    count=1
    args=()
    if [[ "$mode" == final ]]; then count=12; args+=(final); fi
    workspace/Checks/SingleClock20261102/build/VE203TpuBackend workspace/Sw/Soc.bin workspace/Sim/out/Soc "$count" "${args[@]}"
done
Model/.venv/bin/python Model/CheckSoc.py --vectors workspace/Sim/out/Soc
