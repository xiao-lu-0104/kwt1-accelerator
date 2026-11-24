"""POSIX runner integration tests with fake EDA tools; no synthesis claims."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


@unittest.skipIf(os.name == 'nt', 'POSIX process groups and bash required')
class RunnerTest(unittest.TestCase):
    def run_case(self, mode='ok', tamper=False, from_path=False):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / 'tools').mkdir()
            (out / 'source').mkdir()
            shutil.copy2(HERE / 'Run.sh', out / 'tools/Run.sh')
            shutil.copy2(ROOT / 'Server/SystemBackend/StageWatch.py', out / 'tools/StageWatch.py')
            (out / 'tools/VerifyMacro.py').write_text('import pathlib,sys\npathlib.Path(sys.argv[2]).write_text("{}")\n')
            (out / 'std.db').write_text('fixture')
            (out / 'SourceProvenance.json').write_text('{}')
            fake = out / 'fake_dc'
            fake.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
out = pathlib.Path(os.environ['TPU_ASIC_OUT'])
if sys.argv[-1].endswith('CompileSpLib.tcl'):
    pathlib.Path(os.environ['TPU_SRAM_DB']).write_text('fixture db')
    print('SP_LIBRARY_COMPLETE: fixture')
else:
    if os.environ['TEST_MODE'] == 'error':
        print('Error: fake tool error even though exit is zero')
    if os.environ['TEST_MODE'] != 'missing':
        for stem in ('baseline', 'candidate'):
            for ext in ('ddc', 'v', 'sdc'):
                (out/(stem+'.'+ext)).write_text('fixture')
        (out/'guidance.svf').write_text('fixture svf')
        (out/'summary.txt').write_text('SETUP_STATUS: FAIL\\nHOLD_STATUS: FAIL\\n')
        for name in ('check_design', 'check_timing'):
            (out/(name+'.rpt')).write_text('fixture review')
    print('SHARED_ASIC_REPORTS_COMPLETE: fixture')
''')
            fake.chmod(0o755)
            (out / 'MANIFEST.sha256').write_text(''.join(
                hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(out).as_posix() + '\n'
                for p in sorted(out.rglob('*')) if p.is_file()))
            if tamper:
                (out / 'SourceProvenance.json').write_text('tampered')
            env = dict(os.environ, DC_BIN=str(fake), LC_BIN=str(fake),
                       TPU_STDCELL_DB=str(out / 'std.db'), TEST_MODE=mode)
            if from_path:
                env.pop('DC_BIN', None)
                (out / 'dc_shell').symlink_to(fake)
                env['PATH'] = str(out) + os.pathsep + env['PATH']
            result = subprocess.run(['bash', str(out / 'tools/Run.sh'), str(out)],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            return result.returncode, result.stdout.decode()

    def test_failed_timing_reports_preserved_not_promoted_to_pass(self):
        code, output = self.run_case()
        self.assertEqual(code, 0, output)
        self.assertIn('SETUP_STATUS: FAIL', output)
        self.assertIn('REVIEW_PENDING', output)

    def test_native_error_with_zero_exit_rejected(self):
        code, output = self.run_case('error')
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('RESULT: NEW_ACCELERATOR_DC_REPORTS_COMPLETE', output)

    def test_dc_resolved_from_path(self):
        code, output = self.run_case(from_path=True)
        self.assertEqual(code, 0, output)
        self.assertIn('DC_BIN:', output)

    def test_missing_checkpoint_rejected(self):
        code, output = self.run_case('missing')
        self.assertNotEqual(code, 0, output)

    def test_payload_change_rejected_before_tool(self):
        code, output = self.run_case(tamper=True)
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('STAGE_FINISHED:', output)


if __name__ == '__main__':
    unittest.main()
