from pathlib import Path
import hashlib
import importlib.util
import os
import re
import subprocess
import uuid

root = Path(__file__).resolve().parents[1]
base = root / 'release/kwt_postscript_fixture'
base.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('datasheets', root / 'tools/read_kwt_sram_datasheets.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
ghostscript = 'D:/texlive/2026/bin/windows/rungs.exe'
assert Path(ghostscript).is_file()
os.environ['KWT_GHOSTSCRIPT'] = ghostscript
ps = b'''%!PS-Adobe-3.0
%%Pages: 2
/Helvetica findfont 12 scalefont setfont
72 740 moveto (TEST FIXTURE, not vendor data) show
72 720 moveto (RAMTP1024X16 TT 1.10 V 25 C) show
72 700 moveto (CLKA and CLKB use a common clock.) show
72 680 moveto (Read and write operate synchronously.) show
showpage
72 720 moveto (Collision: same address read and write.) show
72 700 moveto (Hold requirement \(test\): 0.10 ns.) show
showpage
%%EOF
'''
units, errors = reader.extract(ps, 'fixture_TT.PS', str(base))
assert not errors, errors
text = re.sub(r'\s+', ' ', units[0][2])
assert 'PostScript via rungs.exe' in units[0][1], units[0][1]
assert 'common clock' in text and 'Collision: same address' in text and '(test): 0.10 ns' in text, text
print('PASS: actual Ghostscript 10.06 converts two-page PostScript, including text on page 2 and escaped parentheses')

# All converters unavailable must remain an explicit extraction failure.
original_call = reader.subprocess.check_call
reader.subprocess.check_call = lambda *a, **k: (_ for _ in ()).throw(OSError('fixture unavailable'))
units, errors = reader.extract(ps, 'no_converter.ps', str(base))
assert not units and errors and 'unavailable/failed' in errors[0][1]
# Failed partial output must not be accepted by a later empty-success converter.
calls = []
def partial_or_empty(command, **kwargs):
    calls.append(command[0])
    outputs = [arg[len('-sOutputFile='):] for arg in command if arg.startswith('-sOutputFile=')]
    if len(calls) == 1:
        Path(outputs[0]).write_text('PARTIAL UNTRUSTED OUTPUT')
        raise subprocess.CalledProcessError(1, command)
    return 0
reader.subprocess.check_call = partial_or_empty
units, errors = reader.extract(ps, 'partial_failure.ps', str(base))
assert not units and errors
reader.subprocess.check_call = original_call
print('PASS: converter failures and stale/partial output cannot become successful datasheet evidence')

original_pdf_text = reader.pdf_text
def fallback_pdf(command, **kwargs):
    if command[0] != 'ps2pdf':
        raise OSError('fixture txtwrite and ps2ascii unavailable')
    Path(command[-1]).write_bytes(b'%PDF-1.4\nfixture PDF')
    return 0
reader.subprocess.check_call = fallback_pdf
reader.pdf_text = lambda *a: ('CLKA CLKB fallback fixture text', 'fixture PDF text converter')
units, errors = reader.extract(ps, 'fallback_pdf.ps', str(base))
assert not errors and 'PostScript via ps2pdf;' in units[0][1]
assert 'fallback fixture text' in units[0][2]
reader.pdf_text = original_pdf_text
reader.subprocess.check_call = original_call
print('PASS: ps2pdf/PDF-text fallback when direct PostScript text converters are unavailable')

library = base / 'library/RAMTP1024X16/datasheet'
library.mkdir(parents=True, exist_ok=True)
ff = library / 'RAMTP1024X16_ff_1p10v_1p10v_0c.ps'
tt = library / 'RAMTP1024X16_tt_1p10v_1p10v_25c.ps'
ff.write_bytes(ps)
tt.write_bytes(ps)
digest = hashlib.sha256(tt.read_bytes()).hexdigest()
output = base / ('report_' + uuid.uuid4().hex[:8])
command = ['python', str(root / 'tools/read_kwt_sram_datasheets.py'), '--root', str(base / 'library'), '--out-dir', str(output)]
result = subprocess.run(command, capture_output=True, text=True)
assert result.returncode == 0, (result.stdout, result.stderr)
assert 'READ_DATASHEET: ' + str(tt) in result.stdout
assert 'READ_DATASHEET: ' + str(ff) not in result.stdout
assert digest == hashlib.sha256(tt.read_bytes()).hexdigest()
assert 'SHA256=' + digest in (output / 'inventory.txt').read_text()
assert 'common clock' in (output / 'summary.txt').read_text()
output2 = base / ('report_' + uuid.uuid4().hex[:8])
result = subprocess.run(command[:-1] + [str(output2), '--max-docs', '2'], capture_output=True, text=True)
assert result.returncode == 0, (result.stdout, result.stderr)
assert result.stdout.index('READ_DATASHEET: ' + str(tt)) < result.stdout.index('READ_DATASHEET: ' + str(ff))
print('PASS: real CLI conversion, TT-only default, TT-first multi-document order, source SHA256 unchanged')
subprocess.run(['python', str(root / 'release/test_kwt_datasheets_sdc.py')], check=True)
