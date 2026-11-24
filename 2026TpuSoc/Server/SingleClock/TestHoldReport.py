"""Read-only recovery reporting checks, using disposable snapshots only."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import HoldReport as report


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tpusoc-hold-report-')
        self.work = Path(self.temp.name)
        checkpoint = self.work/'fixture.ddc'
        checkpoint.write_bytes(b'FAKE DDC')
        (self.work/'report_inputs.json').write_text(json.dumps(dict(inputs=[dict(
            path=str(checkpoint), sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest())])))
        for folder in ('baseline', 'candidate'):
            target = self.work/folder
            target.mkdir()
            (target/'outside_cells.tsv').write_text('Cpu/g0\tFF\n')
            (target/'timing_signature.txt').write_text('clock and budgets fixture\n')
            hold = '-0.120269' if folder == 'baseline' else '0.0042'
            (target/'metrics.tsv').write_text('SETUP_WNS_NS\t0.000449181\nHOLD_WNS_NS\t'+hold+
                '\nSRAM_INPUT_HOLD_WNS_NS\t'+hold+'\nAREA\t728223\n')

    def tearDown(self):
        self.temp.cleanup()

    def run_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            report.compare(str(self.work))
        return (self.work/'hold_report_summary.txt').read_text()

    def test_unchanged_cells_positive_timing(self):
        summary = self.run_report()
        self.assertIn('TIMING_REPAIR_STATUS: PASS', summary)
        self.assertIn('CANDIDATE_REVIEW: OUTSIDE_REFERENCES_UNCHANGED', summary)

    def test_constant_differences_reported_without_hiding_wns(self):
        (self.work/'candidate/outside_cells.tsv').write_text('Cpu/g0\tFF\nCpu/c0\t**logic_0**\n')
        summary = self.run_report()
        self.assertIn('AFTER_HOLD_WNS_NS: 0.0042', summary)
        self.assertIn('OUTSIDE_PSEUDO_CONSTANT_CHANGES: 1', summary)
        self.assertIn('CANDIDATE_REVIEW: PENDING_OUTSIDE_CHANGE_REVIEW', summary)

    def test_changed_cpu_cell_requires_review(self):
        (self.work/'candidate/outside_cells.tsv').write_text('Cpu/g0\tOTHER_FF\n')
        summary = self.run_report()
        self.assertIn('OUTSIDE_REAL_CELL_CHANGES: 1', summary)
        self.assertIn('CPU_REAL_CELL_CHANGES: 1', summary)
        self.assertIn('PENDING_OUTSIDE_CHANGE_REVIEW', summary)

    def test_changed_timing_not_pass(self):
        (self.work/'candidate/timing_signature.txt').write_text('changed budget\n')
        summary = self.run_report()
        self.assertIn('TIMING_REQUIREMENTS: CHANGED', summary)
        self.assertIn('TIMING_REPAIR_STATUS: FAIL', summary)

    def test_negative_hold_not_pass(self):
        p = self.work/'candidate/metrics.tsv'
        p.write_text(p.read_text().replace('0.0042', '-0.000001'))
        self.assertIn('TIMING_REPAIR_STATUS: FAIL', self.run_report())

    def test_input_changes_rejected(self):
        (self.work/'fixture.ddc').write_bytes(b'CHANGED')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.run_report()

    def test_rename_add_remove_and_pseudo_flip_all_listed(self):
        changes = report.differences({'Cpu/old': 'FF', 'Cpu/c': '**logic_0**'},
                                     {'Cpu/new': 'FF', 'Cpu/c': '**logic_1**'})
        self.assertEqual(len(changes), 3)
        self.assertEqual(sum(row[0] == 'REAL_CELL' for row in changes), 2)
        self.assertEqual(sum(row[0] == 'PSEUDO_CONSTANT' for row in changes), 1)


if __name__ == '__main__':
    unittest.main()
