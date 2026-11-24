"""Diagnostic comparisons and provenance checks; no hardware correctness claims."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import Review


class ReviewTest(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX process group wrapper required')
    def test_two_checkpoint_diagnosis_preserves_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, out = root / 'original', root / 'review'
            (run / 'mapped').mkdir(parents=True)
            (run / 'logs').mkdir()
            out.mkdir()
            (run / 'source.sv').write_text('fixture original source')
            (run / 'MANIFEST.sha256').write_text(Review.sha(run / 'source.sv') + '  source.sv\n')
            manifest_sha = Review.sha(run / 'MANIFEST.sha256')
            for stem in ('baseline', 'candidate'):
                for ext in ('ddc', 'v', 'sdc'):
                    (run / 'mapped' / (stem + '.' + ext)).write_text('fixture ' + ext)
            (run / 'mapped/guidance.svf').write_text('fixture svf')
            (run / 'logs/dc.log').write_text('SHARED_ASIC_ERROR: Outside-SRAM leaf count changed')
            libs = [root / 'std.db', root / 'sram.db']
            for path in libs:
                path.write_text('fixture library')
            (run / 'library_sha256.txt').write_text(''.join(Review.sha(p) + '  ' + str(p) + '\n' for p in libs))
            here = Path(__file__).resolve().parent
            shutil.copy2(here.parents[1] / 'Server/SystemBackend/StageWatch.py', out / 'StageWatch.py')
            fake = root / 'fake_dc'
            fake.write_text('''#!/usr/bin/env python3
import os,pathlib
out=pathlib.Path(os.environ['TPU_REVIEW_OUT'])
text='name\\tref\\tregion\\nregister\\tDFF\\toutside\\n'
if out.name=='candidate': text+='new_buffer\\tBUF\\toutside\\n'
(out/'leaves.tsv').write_text(text)
(out/'summary.txt').write_text('SETUP_WNS_NS: -0.1\\n')
print('CHECKPOINT_REVIEW_COMPLETE: fixture')
''')
            fake.chmod(0o755)
            result = subprocess.run(['python3', str(here / 'Review.py'), '--manifest-sha', manifest_sha,
                '--out', str(out), '--run', str(run)], env=dict(os.environ, DC_BIN=str(fake)),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout.decode())
            summary = json.loads((out / 'ReviewSummary.json').read_text())
            self.assertEqual(summary['outside_sram_changes'], 1)
            self.assertIn('no synthesis acceptance', summary['acceptance'])
            self.assertTrue(json.loads((out / 'SourceUnchanged.json').read_text())['unchanged'])
            self.assertTrue((out / 'DcReviewReports.tar.gz').is_file())

    def test_added_removed_and_replaced_outside_leaves_retained(self):
        a = {'same': {'name': 'same', 'ref': 'BUF', 'region': 'outside'},
             'constant': {'name': 'constant', 'ref': '**logic_0**', 'region': 'outside'},
             'replaced': {'name': 'replaced', 'ref': 'DFF1', 'region': 'outside'}}
        b = {'same': a['same'], 'replaced': {'name': 'replaced', 'ref': 'DFF2', 'region': 'outside'},
             'buffer': {'name': 'buffer', 'ref': 'BUF', 'region': 'outside'}}
        result = Review.difference(a, b)
        self.assertEqual({r['name']: r['kind'] for r in result},
                         {'constant': 'removed', 'buffer': 'added', 'replaced': 'ref_changed'})

    def test_manifest_and_changed_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            (run / 'source.sv').write_text('frozen')
            manifest = run / 'MANIFEST.sha256'
            manifest.write_text(Review.sha(run / 'source.sv') + '  source.sv\n')
            expected = Review.sha(manifest)
            Review.verify_manifest(run, expected)
            (run / 'source.sv').write_text('changed')
            with self.assertRaises(ValueError):
                Review.verify_manifest(run, expected)

    def test_duplicate_leaf_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'leaves.tsv'
            path.write_text('name\tref\tregion\nx\tBUF\toutside\nx\tDFF\toutside\n')
            with self.assertRaises(ValueError):
                Review.leaves(path)

    def test_timing_budget_change_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = [Path(temp) / name for name in ('a.sdc', 'b.sdc')]
            a.write_text('create_clock -period 6.666667 clk\nset_fix_hold CoreClock\n')
            b.write_text('create_clock -period 6.666667 clk\nset_dont_touch SRAM\n')
            self.assertEqual(Review.timing_lines(a), Review.timing_lines(b))
            b.write_text('create_clock -period 7 clk\n')
            self.assertNotEqual(Review.timing_lines(a), Review.timing_lines(b))


if __name__ == '__main__':
    unittest.main()
