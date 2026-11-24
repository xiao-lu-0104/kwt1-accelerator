"""Exercise the actual new launcher and runner using fake EDA, never claim DC."""
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
ENTRY = ROOT / 'workspace/Server/tpusoc_frontend_20261110_707cd7f_v1.sh'


@unittest.skipIf(os.name == 'nt', 'Actual bash/process-group tests run in WSL')
class Flow(unittest.TestCase):
    def test_frozen_payload_and_sources(self):
        text = ENTRY.read_text()
        payload = text.split("<<'FRONTEND_707CD7F_PAYLOAD'\n", 1)[1].split('FRONTEND_707CD7F_PAYLOAD\n', 1)[0]
        data = base64.b64decode(payload)
        self.assertIn(hashlib.sha256(data).hexdigest() + '  $work/payload.tar.gz', text)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            files = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
        for line in files['MANIFEST.sha256'].decode().splitlines():
            digest, name = line.split(None, 1)
            self.assertEqual(digest, hashlib.sha256(files[name.strip()]).hexdigest(), name)
        self.assertEqual(json.loads(files['SourceProvenance.json'])['frontend_revision'],
                         '707cd7f4a0a4d416d11bac71112980079e0a9d34')
        for name in ('Run.sh', 'Run.tcl', 'Probe.py'):
            self.assertEqual(files['tools/' + name], (HERE / name).read_bytes())

    def run_case(self, mode='ok', tamper=False, rerun=False):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            # Existing historical files must survive both the real probe and fake DC.
            old = home / 'soc/tpusoc_full_pr_20261109_sentinel'
            old.mkdir(parents=True)
            sentinel = old / 'runner.log'
            sentinel.write_text('HISTORICAL_PR_RUNNING_SENTINEL\n')
            env = dict(os.environ, HOME=str(home), TEST_MODE=mode)
            first = subprocess.run(['bash', str(ENTRY)], env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=20)
            self.assertEqual(first.returncode, 0, first.stdout.decode())
            self.assertIn('PROBE_ONLY_COMPLETE', first.stdout.decode())
            work, = (home / 'soc').glob('tpusoc_frontend_20261110_707cd7f_*')
            self.assertFalse((work / 'mapped').exists())
            self.assertEqual(json.loads((work / 'ServerProbe.json').read_text())['old_pr'][0]
                             ['tails']['runner.log'], sentinel.read_text())
            # Replace only external vendor/EDA actions in this disposable test fixture.
            (work / 'tools/VerifyMacro.py').write_text('from pathlib import Path\nPath("vendor_inputs.json").write_text("{}")\n')
            fake = home / 'fake_dc'
            fake.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
out=Path(os.environ['TPU_ASIC_OUT'])
if sys.argv[-1].endswith('CompileSpLib.tcl'):
    Path(os.environ['TPU_SRAM_DB']).write_text('FAKE_DB')
    print('SP_LIBRARY_COMPLETE: TEST_FIXTURE')
else:
    if os.environ['TEST_MODE']=='error':print('Error: TEST_ZERO_EXIT_ERROR')
    if os.environ['TEST_MODE']!='missing':
        for name in 'baseline.ddc baseline.v baseline.sdc candidate.ddc candidate.v candidate.sdc guidance.svf candidate_leaves.tsv outside_before.tsv outside_after.tsv check_design.rpt check_timing.rpt'.split():
            (out/name).write_text('TEST_ONLY')
        (out/'summary.txt').write_text('SETUP_STATUS: FAIL\\nHOLD_STATUS: FAIL\\nOUTSIDE_SRAM_REFERENCES: REVIEW_REQUIRED\\n')
    print('SHARED_ASIC_REPORTS_COMPLETE: TEST_FIXTURE')
''')
            fake.chmod(0o755)
            std = home / 'std.db'
            std.write_text('FAKE_STD_DB')
            env.update(DC_BIN=str(fake), LC_BIN=str(fake), TPU_STDCELL_DB=str(std))
            ledger = work / 'MANIFEST.sha256'
            lines = []
            for line in ledger.read_text().splitlines():
                _, name = line.split(None, 1)
                lines.append(hashlib.sha256((work / name.strip()).read_bytes()).hexdigest() + '  ' + name.strip())
            ledger.write_text('\n'.join(lines) + '\n')
            if tamper:
                (work / 'SourceProvenance.json').write_text('tampered')
            cmd = ['bash', str(work / 'tools/Run.sh'), str(work)]
            run = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            self.assertEqual(sentinel.read_text(), 'HISTORICAL_PR_RUNNING_SENTINEL\n')
            if rerun:
                before = (work / 'mapped/candidate.v').read_bytes()
                second = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
                self.assertNotEqual(second.returncode, 0)
                self.assertEqual(before, (work / 'mapped/candidate.v').read_bytes())
            return run.returncode, run.stdout.decode()

    def test_native_fail_timing_preserved_and_rerun_refused(self):
        code, log = self.run_case(rerun=True)
        self.assertEqual(code, 0, log)
        self.assertIn('HOLD_STATUS: FAIL', log)
        self.assertIn('OUTSIDE_SRAM_REFERENCES: REVIEW_REQUIRED', log)

    def test_zero_exit_native_error_rejected(self):
        code, log = self.run_case('error')
        self.assertNotEqual(code, 0, log)

    def test_missing_outputs_rejected(self):
        code, log = self.run_case('missing')
        self.assertNotEqual(code, 0, log)

    def test_manifest_tamper_rejected_before_dc(self):
        code, log = self.run_case(tamper=True)
        self.assertNotEqual(code, 0, log)
        self.assertNotIn('STAGE_FINISHED:', log)


if __name__ == '__main__':
    unittest.main()
