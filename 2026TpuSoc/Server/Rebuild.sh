#!/usr/bin/env bash
# Rebuild the pinned project's original Makefile, without editing its RTL/tests.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$root"
target=${1:-test}
case "$target" in test|soc|official|soc-sim|lint|soc-lint|cdc|sram-model|arithmetic|nice) ;; *) echo 'Unsupported build target'; exit 2;; esac
mkdir -p workspace/HostTools workspace/Checks
export LDFLAGS=-static
if ! command -v riscv64-unknown-elf-gcc >/dev/null && command -v riscv64-linux-gnu-gcc >/dev/null; then
    for tool in gcc objcopy objdump; do
        program=$(command -v "riscv64-linux-gnu-$tool")
        if [[ "$tool" == gcc ]]; then
            # Linux distro GCC defaults to PIE; freestanding startup needs direct addresses.
            printf '#!/usr/bin/env bash\nexec %q -fno-pie -no-pie "$@"\n' "$program" > "workspace/HostTools/riscv64-unknown-elf-$tool"
        else
            printf '#!/usr/bin/env bash\nexec %q "$@"\n' "$program" > "workspace/HostTools/riscv64-unknown-elf-$tool"
        fi
        chmod +x "workspace/HostTools/riscv64-unknown-elf-$tool"
    done
    export PATH="$root/workspace/HostTools:$PATH"
    echo 'FIRMWARE_TOOLCHAIN: riscv64-linux-gnu freestanding RV32IMAC (no libc)'
fi
echo "SOURCE_COMMIT: $(git rev-parse HEAD)"
verilator --version
g++ --version | head -n 1
Model/.venv/bin/python -c 'import sys,numpy;print("PYTHON:",sys.version.split()[0],"NUMPY:",numpy.__version__)'
if [[ -f Server/Backend/LocalReset.vlt ]]; then
    make "$target" 'Warnings=-Wall -Wno-UNUSEDPARAM -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY Server/Backend/LocalReset.vlt'
else
    make "$target"
fi
