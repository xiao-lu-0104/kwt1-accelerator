from pathlib import Path
import gzip
import importlib.util
import io
import subprocess
import tkinter
import zipfile

root = Path(__file__).resolve().parents[1]
base = root / 'release/kwt_datasheet_fixture'
base.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('datasheets', root / 'tools/read_kwt_sram_datasheets.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

html = b'<html><style>hidden</style><body><h1>Synchronous operation</h1><p>CLKA &amp; CLKB share a common clock.</p><table><tr><td>Collision</td><td>same address read and write</td></tr></table></body></html>'
units, failures = module.extract(html, 'data.HTM', str(base))
assert not failures and units[0][1] == 'HTML'
assert 'CLKA & CLKB share a common clock.' in units[0][2]
assert 'hidden' not in units[0][2] and module.excerpts(units[0][2])
units, failures = module.extract(gzip.compress(html), 'data.gz', str(base))
assert not failures and units[0][1] == 'HTML'
archive = io.BytesIO()
with zipfile.ZipFile(archive, 'w') as stream:
    stream.writestr('../../escape.ds', 'same clock read and write\n')
units, failures = module.extract(archive.getvalue(), 'data.zip', str(base))
assert not failures and 'same clock' in units[0][2]
assert not (base.parent.parent / 'escape.ds').exists()
_, failures = module.extract(b'\x00binary', 'data.bin', str(base))
assert failures
_, failures = module.extract(b'%!PS-Adobe\nnot plain text', 'data.ps', str(base))
assert failures
paths = ['x/datasheet/generic.DS', 'x/datasheet/foo_tt_1p10v_1p10v_25c.HTML', 'x/datasheet/foo_ss_1p00v_25c.html', 'x/datasheet/logo.png']
assert module.pick_documents(paths, 2) == [paths[1], paths[0]]
# Missing converter must remain unresolved; no fake readable-PDF success.
original = module.subprocess.check_output
module.subprocess.check_output = lambda *a, **k: (_ for _ in ()).throw(OSError('fixture missing converter'))
_, failures = module.extract(b'%PDF-1.4\nfixture', 'data.PDF', str(base))
assert failures and 'unavailable/failed' in failures[0][1]
module.subprocess.check_output = original
print('PASS: HTML/plain/gzip/ZIP content detection, no archive path extraction, document priority, unsupported formats/converters')

library = base / 'libroot/RAMTP1024X16/datasheet/nested'
library.mkdir(parents=True, exist_ok=True)
(library / 'RAMTP1024X16_tt_1p10v_1p10v_25c.HTML').write_bytes(html)
(library / 'RAMTP1024X16_ss_0p9v_25c.html').write_bytes(html)
output = base / ('report_' + __import__('uuid').uuid4().hex[:8])
command = ['python', str(root / 'tools/read_kwt_sram_datasheets.py'), '--root', str(base / 'libroot'), '--out-dir', str(output), '--max-docs', '1']
result = subprocess.run(command, capture_output=True, text=True)
assert result.returncode == 0, (result.stdout, result.stderr)
assert 'EXTRACTION_COMPLETE' in result.stdout and 'DATASHEET_LINE_' in result.stdout
assert len(list(output.glob('RAMTP1024X16_*.txt'))) == 1
assert '_ss_' in (output / 'inventory.txt').read_text()
result = subprocess.run(command, capture_output=True, text=True)
assert result.returncode == 2 and 'must be new' in result.stderr
broken = base / 'brokenroot/RAMTP1024X16/datasheet'
broken.mkdir(parents=True, exist_ok=True)
(broken / 'bad.ds').write_bytes(b'\x00binary')
output_bad = base / ('broken_' + __import__('uuid').uuid4().hex[:8])
result = subprocess.run(['python', str(root / 'tools/read_kwt_sram_datasheets.py'), '--root', str(base / 'brokenroot'), '--out-dir', str(output_bad)], capture_output=True, text=True)
assert result.returncode == 2 and 'EXTRACTION_UNRESOLVED' in result.stdout and 'EXTRACTION_INCOMPLETE' in result.stdout
print('PASS: recursive/case-insensitive content read, UTF-8 evidence, inventory, no report overwrite, truthful failed extraction status')

tcl = tkinter.Tcl()
calls = []
def register(command):
    tcl.createcommand(command, lambda *args: calls.append((command, args)) or '')
for command in ('create_clock', 'set_clock_uncertainty', 'set_clock_transition', 'set_input_delay', 'set_output_delay', 'set_load'):
    register(command)
tcl.createcommand('get_ports', lambda name: (name,))
tcl.createcommand('get_clocks', lambda name: (name,))
tcl.createcommand('all_inputs', lambda: ('clk', 'rst_n', 'input'))
tcl.createcommand('all_outputs', lambda: ('busy', 'output'))
tcl.createcommand('remove_from_collection', lambda a, b: tuple(x for x in tcl.splitlist(a) if x not in tcl.splitlist(b)))
tcl.call('source', str(root / 'syn/kwt_encoder_12.sdc'))
assert len(calls) == 9, calls
assert calls[0] == ('create_clock', ('-name', 'clk', '-period', '6.667', 'clk'))
assert ('set_clock_uncertainty', ('-setup', '1.0', 'clk')) in calls
assert ('set_clock_uncertainty', ('-hold', '1.0', 'clk')) in calls
for direction in ('input', 'output'):
    for mode in ('-max', '-min'):
        found = [args for cmd, args in calls if cmd == 'set_' + direction + '_delay' and mode in args]
        assert len(found) == 1 and '0.5' in found[0]
        if direction == 'input': assert tcl.splitlist(found[0][-1]) == ('rst_n', 'input')
assert calls[-1] == ('set_load', ('0.02', 'busy output'))
print('PASS: independent SDC preserves baseline clock, setup/hold budgets and both IO bounds, including reset constraints')
