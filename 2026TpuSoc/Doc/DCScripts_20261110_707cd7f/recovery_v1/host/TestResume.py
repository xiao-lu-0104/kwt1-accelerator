"""Recovery integration in isolated HOME with fake EDA; not design validation."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ENTRY = ROOT / 'workspace/Server/tpusoc_hold_recovery_20261110_707cd7f_v1.sh'


def extract_fixture(entry, marker, target):
    data = base64.b64decode(entry.read_text().split("<<'" + marker + "'\n", 1)[1].split(marker + '\n', 1)[0])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for m in archive.getmembers():
            path = target / m.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(m).read())


@unittest.skipIf(os.name == 'nt', 'Bash integration runs in WSL')
class Resume(unittest.TestCase):
    def test_payload_and_tcl_no_rtl_resynthesis(self):
        text = (HERE / 'Resume.tcl').read_text()
        self.assertNotIn('if {![compile_ultra', text)
        self.assertNotIn('analyze -format', text)
        self.assertIn('read_ddc [file join $Input baseline.ddc]', text)
        self.assertIn('compile -incremental_mapping -only_hold_time', text)
        self.assertLess(text.index('write -hierarchy -format ddc -output [file join $Out candidate.ddc]'),
                        text.index('report_area -hierarchy'))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            extract_fixture(ENTRY, 'HOLD_RECOVERY_707CD7F', out)
            for name in ('Resume.tcl', 'Resume.py'):
                self.assertEqual((out / 'tools' / name).read_bytes(), (HERE / name).read_bytes())
            result = subprocess.run(['sha256sum', '--quiet', '-c', 'PACKAGE.sha256'], cwd=out)
            self.assertEqual(result.returncode, 0)
        tcl = subprocess.run(['tclsh'], input=('set f [open {' + str(HERE / 'Resume.tcl') + '} r]\n'
            'set s [read $f]\nclose $f\nif {![info complete $s]} {exit 1}\n').encode())
        self.assertEqual(tcl.returncode, 0)

    def case(self, mode='ok', preflight=None):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            run = home / 'soc/tpusoc_frontend_20261110_707cd7f_ZKpdeM'
            run.mkdir(parents=True)
            extract_fixture(ROOT / 'workspace/Server/tpusoc_frontend_20261110_707cd7f_v1.sh',
                            'FRONTEND_707CD7F_PAYLOAD', run)
            (run / 'mapped').mkdir()
            (run / 'logs').mkdir()
            (run / 'dc_attempt').mkdir()
            for ext in ('ddc', 'v', 'sdc'):
                (run / ('mapped/baseline.' + ext)).write_text('TEST_BASELINE_' + ext)
            (run / 'logs/dc.log').write_text('DC_STAGE: compile_start\nDC_STAGE: baseline_saved\nDC_STAGE: sram_hold_start\nReceived Signal 15\n')
            (run / 'dc_attempt/runner.log').write_text('STAGE_TIMEOUT: accelerator_707cd7f_dc\nRUN_EXIT: 124 STAGE: dc\n')
            std = home / 'std.db'
            std.write_text('TEST_STD')
            ram = run / 'RAMSP1024X16_tt_1p10v_1p10v_25c.db'
            ram.write_text('TEST_RAM')
            (run / 'library_sha256.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p) + '\n' for p in (std, ram)))
            if preflight == 'tamper':
                (run / 'source/TpuTop.sv').write_text('TAMPERED')
            if preflight == 'candidate':
                (run / 'mapped/candidate.ddc').write_text('NEWER_CANDIDATE')
            if preflight == 'library':
                ram.write_text('CHANGED_LIBRARY')
            before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in run.rglob('*') if p.is_file()}
            fake = home / 'fake_dc'
            fake.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
out=Path(os.environ['TPU_ASIC_OUT'])
mode=os.environ['TEST_MODE']
for name in 'candidate.ddc candidate.v candidate.sdc guidance.svf summary.txt candidate_leaves.tsv outside_before.tsv outside_after.tsv ReloadBaselineSummary.txt reload_baseline.sdc area.rpt units.rpt check_design.rpt check_timing.rpt setup.rpt hold.rpt'.split():
    if mode=='missing' and name=='candidate.ddc': continue
    (out/name).write_text('TEST_FIXTURE; HOLD_STATUS: FAIL; OUTSIDE_SRAM_REFERENCES: REVIEW_REQUIRED')
if mode=='error':print('Error: FAKE_ZERO_EXIT_ERROR')
if mode=='mutate':
    (Path.home()/'soc/tpusoc_frontend_20261110_707cd7f_ZKpdeM/mapped/baseline.ddc').write_text('FAKE_EXTERNAL_MUTATION')
print('SHARED_ASIC_REPORTS_COMPLETE: TEST_FIXTURE')
''')
            fake.chmod(0o755)
            result = subprocess.run(['bash', str(ENTRY)], env=dict(os.environ, HOME=str(home), DC_BIN=str(fake), TEST_MODE=mode),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            if mode != 'mutate':
                self.assertTrue(all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in before.items()))
            dirs = list((home / 'soc').glob('tpusoc_hold_recovery_20261110_707cd7f_*'))
            self.assertEqual(len(dirs), 1)
            if preflight:
                self.assertFalse((dirs[0] / 'mapped/dc.log').exists())
            return result.returncode, result.stdout.decode()

    def test_reports_complete_but_timing_and_scope_not_promoted(self):
        code, log = self.case()
        self.assertEqual(code, 0, log)
        self.assertIn('HOLD_STATUS: FAIL', log)
        self.assertIn('REVIEW_PENDING', log)
        self.assertIn('ORIGINAL_INPUTS_UNCHANGED: True', log)

    def test_zero_exit_native_error_rejected(self):
        code, log = self.case('error')
        self.assertNotEqual(code, 0, log)

    def test_missing_candidate_rejected(self):
        code, log = self.case('missing')
        self.assertNotEqual(code, 0, log)

    def test_original_mutation_detected(self):
        code, log = self.case('mutate')
        self.assertNotEqual(code, 0, log)
        self.assertIn('ORIGINAL_INPUTS_UNCHANGED: False', log)

    def test_original_source_tamper_stops_before_eda(self):
        code, log = self.case(preflight='tamper')
        self.assertNotEqual(code, 0, log)

    def test_newer_candidate_prevents_discarding_progress(self):
        code, log = self.case(preflight='candidate')
        self.assertNotEqual(code, 0, log)

    def test_changed_library_stops_before_eda(self):
        code, log = self.case(preflight='library')
        self.assertNotEqual(code, 0, log)


if __name__ == '__main__':
    unittest.main()
