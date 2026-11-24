#!/usr/bin/env bash
set -euo pipefail
echo '=== disk ==='
df -h "$HOME" /tmp
df -i "$HOME" /tmp
echo '=== runtime ==='
python3 -c 'import sys,platform,importlib.util; print(sys.version); print(platform.platform()); print("numpy:",bool(importlib.util.find_spec("numpy"))); print("tensorflow:",bool(importlib.util.find_spec("tensorflow")))'
echo '=== tools ==='
for tool in dc_shell icc2_shell vcs verilator gcc make; do command -v "$tool" || true; done
echo '=== own processes ==='
ps -u "$(id -u)" -o pid,ppid,etime,pcpu,pmem,args
echo 'ENVIRONMENT_PROBE_COMPLETE'
