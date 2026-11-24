#!/usr/bin/env bash
set -euo pipefail
# Install only into a separate /tmp target, never into the system Python.
# This wheel set targets Linux x86_64 CPython 3.6. Use an existing working
# TensorFlow environment instead when the server's Python version differs.
wheels=${1:?usage: bash install_runtime.sh /tmp/server_wheels_py36}
dest=${2:-/tmp/chipdesign_python36_runtime_$(id -u)}
python3 -c 'import sys,platform; assert sys.version_info[:2]==(3,6), "Wheel set requires CPython 3.6"; assert platform.machine()=="x86_64", "Wheel set requires Linux x86_64"'
if [[ -e "$dest" ]]; then echo "Runtime directory already exists: $dest; inspect it before retrying"; exit 2; fi
pipwheel=$(find "$wheels" -maxdepth 1 -name 'pip-21.3.1-*.whl' -print -quit)
[[ -n "$pipwheel" ]] || { echo 'Missing offline pip wheel'; exit 2; }
PYTHONPATH="$pipwheel" python3 -m pip install --no-index --only-binary=:all: \
    --find-links "$wheels" --target "$dest" -r "$wheels/requirements.txt"
PYTHONPATH="$dest" python3 -c 'import tensorflow as tf,numpy as np; print("OFFLINE_RUNTIME_READY",tf.__version__,np.__version__)'
echo "RUNTIME_PATH=$dest"
