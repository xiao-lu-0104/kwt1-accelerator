#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd "$(dirname "$0")" && pwd)
build=$(mktemp -d /tmp/tpusoc_task_window_XXXXXX)
cp "$source_dir/TaskActivity.sv" "$source_dir/TestTaskWindow.sv" "$build/"
cd "$build"
if ! verilator --binary --timing -Wno-fatal +define+TPU_LOCAL_WINDOW_TEST \
    --top-module LocalTaskPowerTop TaskActivity.sv TestTaskWindow.sv > build.log 2>&1; then
    tail -n 65 build.log
    exit 1
fi
echo "TASK_WINDOW_BUILD_DIR: $build"
./obj_dir/VLocalTaskPowerTop +TASK_SAIF=unused.saif
