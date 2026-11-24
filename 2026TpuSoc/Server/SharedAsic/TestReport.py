"""Exercise acceptance distinctions without Synopsys; never label mocks as STA."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import RecoverReport as report


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        source = self.work / 'checkpoint.ddc'
        source.write_bytes(b'fixture checkpoint')
        (self.work / 'ReportInputs.json').write_text(json.dumps(
            {'inputs': {str(source): report.sha(source)}}))
        for mode in ('baseline', 'candidate'):
            directory = self.work / mode
            directory.mkdir()
            (directory / 'cells.tsv').write_text('Bus/g0\tFF\nTpu/Core/Sram/g0\tBUF\n')
            (directory / 'timing_signature.txt').write_text('same mocked budget\n')
            hold = '-0.120269' if mode == 'baseline' else '0.002'
            (directory / 'metrics.tsv').write_text(
                'SETUP_WNS_NS\t0.03\nHOLD_WNS_NS\t' + hold
                + '\nSRAM_INPUT_HOLD_WNS_NS\t' + hold + '\nAREA\t703272.4\nSRAM_AREA\t512317.3832\n')

    def compare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            report.compare(self.work)
        return (self.work / 'summary.txt').read_text()

    def test_reports_positive_timing_without_equivalence_claim(self):
        text = self.compare()
        self.assertIn('TIMING_STATUS: PASS_TT_PRELAYOUT', text)
        self.assertIn('SCOPE_REVIEW: REFERENCES_UNCHANGED', text)
        self.assertIn('NETLIST_EQUIVALENCE: NOT_ESTABLISHED', text)

    def test_outside_added_buffer_requires_review_but_reports_timing(self):
        with (self.work / 'candidate/cells.tsv').open('a') as stream:
            stream.write('Tpu/Core/hold_buf0\tBUF_X1\n')
        text = self.compare()
        self.assertIn('TIMING_STATUS: PASS_TT_PRELAYOUT', text)
        self.assertIn('OUTSIDE_REAL_CELL_CHANGES: 1', text)
        self.assertIn('SCOPE_REVIEW: REQUIRED', text)
        self.assertIn('Tpu/Core/hold_buf0', (self.work / 'cell_changes.tsv').read_text())

    def test_pseudo_constants_are_separately_visible(self):
        with (self.work / 'candidate/cells.tsv').open('a') as stream:
            stream.write('c0\t**logic_0**\n')
        text = self.compare()
        self.assertIn('OUTSIDE_REAL_CELL_CHANGES: 0', text)
        self.assertIn('OUTSIDE_PSEUDO_CONSTANT_CHANGES: 1', text)
        self.assertIn('SCOPE_REVIEW: REQUIRED', text)

    def test_negative_hold_and_changed_requirements_cannot_pass(self):
        path = self.work / 'candidate/metrics.tsv'
        original = path.read_text()
        path.write_text(original.replace('0.002', '-0.000001'))
        self.assertIn('TIMING_STATUS: FAIL', self.compare())
        path.write_text(original)
        (self.work / 'candidate/timing_signature.txt').write_text('changed budget\n')
        self.assertIn('TIMING_REQUIREMENTS: CHANGED', self.compare())
        self.assertIn('TIMING_STATUS: FAIL', self.compare())

    def test_changed_checkpoint_is_rejected(self):
        (self.work / 'checkpoint.ddc').write_bytes(b'changed after capture')
        with self.assertRaisesRegex(ValueError, 'Read-only input changed'):
            self.compare()

    def test_nonfinite_metric_is_rejected(self):
        path = self.work / 'candidate/metrics.tsv'
        path.write_text(path.read_text().replace('0.002', 'nan'))
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            self.compare()

    def test_added_removed_changed_scope_all_listed(self):
        rows = report.differences({'Bus/old': 'FF', 'Tpu/Core/Sram/b': 'BUF', 'c0': '**logic_0**'},
                                  {'Bus/new': 'FF', 'Tpu/Core/Sram/b': 'BUF2', 'c0': '**logic_1**'})
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(row[0] == 'SRAM' for row in rows), 1)
        self.assertEqual(sum(row[1] == 'PSEUDO_CONSTANT' for row in rows), 1)


if __name__ == '__main__':
    unittest.main()
