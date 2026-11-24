"""Validate the exact offline accelerator payload under WSL before transfer."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile

here = Path(__file__).resolve().parent
stage = here / 'checked_payload'
stage.mkdir(exist_ok=True)
with tarfile.open(here / 'payload.tar.gz', 'r:gz') as archive:
    archive.extractall(stage, filter='data')
manifest = json.loads((stage / 'SourceManifest.json').read_text())
for name, expected in manifest['files_sha256'].items():
    assert hashlib.sha256((stage / name).read_bytes()).hexdigest() == expected, name
sources = json.loads((stage / 'AcceleratorSources.json').read_text())
args = ['verilator', '--lint-only', '--timing', '-Wall', '-Wno-UNUSEDPARAM',
        '-Wno-UNUSEDSIGNAL', '-Wno-PINCONNECTEMPTY', '-Wno-DECLFILENAME',
        '-Wno-TIMESCALEMOD', '+define+TPU_SRAM_MODEL', '+define+TPU_MATRIX_ROWS=2',
        '--top-module', 'SubmissionAccelerator']
args += [str(stage / name) for name in sources]
args += ['/mnt/e/chipdesign/2026TpuSoc/Server/Backend/LocalRamspFixture.sv']
(here / 'LintArgs.json').write_text(json.dumps(args, indent=2) + '\n')
result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(here / 'Lint.log').write_text(result.stdout)
print(result.stdout[-12000:])
print('PAYLOAD_FILES_VERIFIED:', len(manifest['files_sha256']))
print('LINT_EXIT:', result.returncode)
raise SystemExit(result.returncode)
