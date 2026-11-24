#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"
echo 'LOCAL_SCOPE: adapter wiring against a test double, not the foundry model'
verilator --binary --timing --assert -Wall -Wno-UNUSEDPARAM -Wno-TIMESCALEMOD -Wno-DECLFILENAME \
    --top-module SpBindingTest +define+TPU_SRAM_MODEL \
    --Mdir workspace/Checks/SpBindingBuild -j 4 \
    Rtl/TpuPkg.sv Rtl/TpuSram.sv Server/Backend/SpFoundry.sv \
    Server/Backend/LocalRamspFixture.sv Server/Backend/SpBindingTest.sv
workspace/Checks/SpBindingBuild/VSpBindingTest
