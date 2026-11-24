#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
work=$(mktemp -d /tmp/tpusoc_cpu_trace_lint_XXXXXX)
python3 "$repo/Server/SharedAsic/TestQualification.py" --fixtures "$work"
python3 "$here/LocalPlatform.py" "$work"
cat > "$work/TraceFixture.sv" <<'SV'
module LocalCpuTraceTop;
SharedTest SharedTest(); TaskActivity TaskActivity(); CpuWriteTrace CpuWriteTrace();
endmodule
module TaskActivity; bit Started=0,Stopped=0; endmodule
module SharedTest;
logic Clock=0,ResetN=0; wire [31:0] Pc; longint unsigned Cycles=0;
e203_cpu_top Cpu(.clk(Clock),.rst_n(ResetN),.inspect_pc(Pc));
endmodule
SV
cd "$work"
if ! verilator --lint-only --timing -Wno-fatal --top-module LocalCpuTraceTop -f CpuLint.f \
    MacroFixture.sv PrivateMacroFixture.sv TraceFixture.sv "$here/CpuWriteTrace.sv" > lint.log 2>&1; then
    tail -n 32 lint.log; exit 1
fi
echo "PASS LOCAL_CPU_TRACE_LINT: original CPU RTL and physical macro hierarchy resolve; comparison platform only; log=$work/lint.log"
