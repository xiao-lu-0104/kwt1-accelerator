from pathlib import Path
import hashlib
import importlib.util
import os
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('arcs', root / 'tools/inspect_kwt_sram_clock_arcs.py')
arcs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arcs)
fixture = '''library(test) {
 time_unit : "1ns";
 /* pin(IGNORED) { timing() { related_pin : "CLKA"; } } */
 cell(RAMTP1024X16) {
  pin("CLKA") {
   timing () { related_pin : "CLKB"; timing_type : hold_rising;
    when : "CENA & CENB";
    rise_constraint(TABLE) { index_1("0.1, 0.2"); values("0.0, -0.01", "0.02, 0.0"); }
   }
  }
  pin(CLKB) { timing () { related_pin : CLKA; timing_type : setup_rising;
   rise_constraint(T) { values("0, 0"); }
  } }
  pin(DB) { timing() { related_pin : "CLKB"; timing_type : hold_rising; } }
 }
}'''
actual = arcs.clock_arcs(fixture)
assert len(actual) == 2, actual
assert actual[0][:4] == ('CLKA', 'CLKB', 'hold_rising', 'CENA & CENB'), actual
assert actual[0][4] == ['rise_constraint min=-0.01 max=0.02'], actual
assert actual[1][:3] == ('CLKB', 'CLKA', 'setup_rising')
assert '$hold' not in arcs.without_comments('// $hold(CLKA, CLKB, 9);\n')
assert arcs.field(fixture, 'time_unit') == '1ns'
try:
    list(arcs.groups('pin(CLKA) { timing() {', 'pin'))
except ValueError:
    pass
else:
    raise AssertionError('malformed Liberty accepted')
print('PASS: balanced Liberty clock groups, quoted/unquoted names, table values, comments and malformed input')

subprocess.run(['python', str(root / 'release/test_kwt_hold_audit.py')], check=True)
base = root / 'release/kwt_hold_audit_fixture'
package, run, binaries = base / 'package', base / 'run', base / 'bin'
# Metadata parsing itself was tested above; this stub keeps the runner fixture private.
(package / 'tools/inspect_kwt_sram_clock_arcs.py').write_text('print("CLOCK_ARC: fixture only")\n')
(binaries / 'dc_shell').write_text('''#!/usr/bin/env bash
set -eu
[[ ${KWT_DC_AUDIT_SRAM_CLOCKS:-} == 1 && $KWT_DC_CHECKPOINT == */hold_pilot_fixture/dc_out_bound/kwt_encoder_12.ddc ]] || exit 7
[[ ${KWT_DC_FIX_HOLD:-} != 1 && -z ${KWT_DC_PILOT_HOLD_NS:-} ]] || exit 8
echo 'CLOCK_AUDIT_DATA_ENDPOINT_HOLD_WNS: 0.010 ns'
echo 'CLOCK_AUDIT_SRAM_CLOCK_PIN_HOLD_WNS: -0.100 ns'
echo 'CLOCK_AUDIT_ACCEPTANCE: NONE'
echo KWT_SRAM_CLOCK_AUDIT_COMPLETE
''', newline='\n')
bash = 'C:/Program Files/Git/bin/bash.exe'
bin_path = '/' + binaries.drive[0].lower() + binaries.as_posix()[2:]
command = f'export PATH="{bin_path}:$PATH"; bash "{(package / "tools/rerun_kwt_sram_synthesis.sh").as_posix()}" --run-dir "{run.as_posix()}" --audit-sram-clocks'
result = subprocess.run([bash, '-c', command], cwd=run, capture_output=True, text=True)
assert result.returncode == 2 and 'no completed, matching mapped pilot checkpoint' in result.stdout, result.stdout
pilot = run / 'hold_pilot_fixture'
(pilot / 'dc_out_bound').mkdir(parents=True, exist_ok=True)
mapped = pilot / 'dc_out_bound/kwt_encoder_12.ddc'
mapped.write_text('completed mapped pilot\n')
provenance = sorted(run.glob('hold_audit_*/verified_input_digest.txt'))[-1].read_text().strip()
(pilot / 'verified_input_digest.txt').write_text(provenance + '\n', newline='\n')
(pilot / 'dc.log').write_text('KWT_DC_COMPLETE\n', newline='\n')
before = mapped.read_bytes()
result = subprocess.run([bash, '-c', command], cwd=run, capture_output=True, text=True)
assert result.returncode == 0, (result.stdout, result.stderr)
assert mapped.read_bytes() == before
summary = sorted(run.glob('hold_clock_audit_*/summary.txt'))[-1].read_text()
assert 'CLOCK_ARC: fixture only' in summary and 'CLOCK_AUDIT_DATA_ENDPOINT_HOLD_WNS: 0.010' in summary
(pilot / 'verified_input_digest.txt').write_text('wrong digest\n', newline='\n')
result = subprocess.run([bash, '-c', command], cwd=run, capture_output=True, text=True)
assert result.returncode == 2, (result.stdout, result.stderr)
print('PASS: clock audit selects only matching mapped pilot, preserves it, rejects stale provenance and writes concise summary')
