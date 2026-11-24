#!/usr/bin/env bash
set -euo pipefail
repo=/mnt/e/chipdesign/2026TpuSoc
out=$(mktemp -d /tmp/tpusoc_system_task_init_XXXXXX)
echo "LOCAL_INIT_BUILD: $out"
python3 "$repo/Server/SharedAsic/TestQualification.py" --fixtures "$out"
python3 "$repo/Server/SystemBackend/TestSystemTasks.py" --fixtures "$out"
cd "$out"
verilator --binary --timing -j 4 -Wno-fatal --top-module LocalInitTop "$repo/Server/SystemBackend/TcmMacro.sv" "$repo/Server/SystemBackend/TcmInitializer.sv" SharedTcmGuard.sv Fixture.sv MacroFixture.sv > build.log 2>&1 || { tail -n 35 build.log; exit 1; }
./obj_dir/VLocalInitTop +FIRMWARE="$out/Firmware.hex" > run.log 2>&1 || { tail -n 25 run.log; exit 1; }
grep -E 'PASS |PHYSICAL_TCM_INIT_FINAL' run.log
if (ulimit -c 0; ./obj_dir/VLocalInitTop +FIRMWARE="$out/Firmware.hex" +BAD_MASK) > bad.log 2>&1; then
    echo 'ERROR: disabled physical writes accepted'; exit 1
fi
grep -q 'TCM_INIT_ITCM_READBACK' bad.log
echo 'PASS LOCAL_INIT_NEGATIVE: broken SRAM write mask fails readback'
