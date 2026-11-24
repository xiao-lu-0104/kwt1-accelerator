#!/usr/bin/env bash
set -euo pipefail
runtime=${CHIPDESIGN_PYTHON_RUNTIME:-/tmp/chipdesign_python36_runtime_$(id -u)}
if [[ -d "$runtime" ]]; then export PYTHONPATH="$runtime${PYTHONPATH:+:$PYTHONPATH}"; fi
export TF_CPP_MIN_LOG_LEVEL=${TF_CPP_MIN_LOG_LEVEL:-2}
exec python3 "$@"
