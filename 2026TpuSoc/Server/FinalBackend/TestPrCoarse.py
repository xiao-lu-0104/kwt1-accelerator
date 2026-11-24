"""Geometry, provenance and native-command orchestration tests; no real ICC2 run."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PrCoarse import geometry, tree_manifest, verify_source, write_svg
from Preflight import sha
from PrStart import SUCCESS

HERE = Path(__file__).resolve().parent


class CoarseTests(unittest.TestCase):
    def geometry_fixture(self, stage, count=56):
        (stage / 'core_bbox.txt').write_text('{0 0} {1000 1000}\n')
        rows = []
        for index in range(count):
            x, y = 10 + index % 8 * 110, 10 + index // 8 * 110
            rows.append(['Storage[{}]/Macro'.format(index), x, y, x + 100, y + 91.485247])
        self.write_boxes(stage, rows)
        (stage / 'report_placement.rpt').write_text('HM to HM overlaps in design top: 0\nTotal hard macro to hard macro overlaps: 0\n')
        self.write_def(stage, rows)
        return rows

    def write_boxes(self, stage, rows):
        with (stage / 'macros.tsv').open('w', newline='') as stream:
            writer = csv.writer(stream, delimiter='\t')
            writer.writerow(['instance', 'x1', 'y1', 'x2', 'y2'])
            writer.writerows(rows)

    def write_def(self, stage, rows, placement='PLACED'):
        entries = ['- {} RAMSP1024X16 + {} ( {} {} ) N ;'.format(row[0], placement, int(row[1]), int(row[2])) for row in rows]
        (stage / 'coarse_floorplan.def').write_text('VERSION 5.8 ;\nCOMPONENTS {} ;\n{}\nEND COMPONENTS\nEND DESIGN\n'.format(len(rows), '\n'.join(entries)))

    def test_56_macros_inside_core_with_native_and_def_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            self.geometry_fixture(stage)
            review = geometry(stage)
            self.assertEqual(review['macro_count'], 56)
            self.assertEqual(review['macro_overlaps'], 0)
            write_svg(stage / 'preview.svg', review)
            import xml.etree.ElementTree as ET
            root = ET.parse(stage / 'preview.svg').getroot()
            self.assertEqual(len(root.findall('{http://www.w3.org/2000/svg}rect')), 57)

    def test_macro_overlap_outside_count_nan_and_wrong_footprint_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            for change, expected in (
                    (lambda rows: rows.__setitem__(1, list(rows[0][0:1]) + rows[0][1:]), 'Duplicate'),
                    (lambda rows: rows.__setitem__(1, [rows[1][0]] + rows[0][1:]), 'overlap'),
                    (lambda rows: rows.__setitem__(0, [rows[0][0], -10, 10, 90, 101.485247]), 'outside'),
                    (lambda rows: rows.__setitem__(0, [rows[0][0], float('nan'), 0, 100, 91.485247]), 'invalid'),
                    (lambda rows: rows.__setitem__(0, [rows[0][0], 0, 0, 100, 100]), 'footprint'),
                    (lambda rows: rows.pop(), 'exactly')):
                rows = self.geometry_fixture(stage)
                change(rows)
                self.write_boxes(stage, rows)
                with self.assertRaisesRegex(ValueError, expected):
                    geometry(stage)

    def test_success_marker_alone_cannot_replace_native_overlap_and_def_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            for native in ('', 'Total hard macro to hard macro overlaps: 1',
                           'Error: geometry problem\nTotal hard macro to hard macro overlaps: 0'):
                self.geometry_fixture(stage)
                (stage / 'report_placement.rpt').write_text(native)
                with self.assertRaisesRegex(ValueError, 'Native'):
                    geometry(stage)
            for placement in ('UNPLACED', 'UNPLACED_EXTRA'):
                rows = self.geometry_fixture(stage)
                self.write_def(stage, rows, placement)
                with self.assertRaisesRegex(ValueError, 'Unplaced'):
                    geometry(stage)
            rows = self.geometry_fixture(stage)
            self.write_def(stage, rows[:-1])
            with self.assertRaisesRegex(ValueError, 'inventory'):
                geometry(stage)

    def test_tree_copy_hashes_reject_mutation_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source.nlib'
            root.mkdir()
            (root / 'data').write_bytes(b'original')
            before = tree_manifest(root)
            copied = root.with_name('copied.nlib')
            shutil.copytree(root, copied)
            self.assertEqual(tree_manifest(copied), before)
            (copied / 'data').write_bytes(b'new placement')
            self.assertEqual(tree_manifest(root), before)
            self.assertNotEqual(tree_manifest(copied), before)
            try:
                (root / 'link').symlink_to(root / 'data')
            except OSError:
                return  # Windows without symlink privilege; Linux runs this branch.
            with self.assertRaisesRegex(ValueError, 'symlink'):
                tree_manifest(root)

    def source_fixture(self, root):
        netlist = root / 'frozen.v'
        netlist.write_text('module frozen; endmodule')
        design = root / 'design'
        design.mkdir()
        (design / 'accelerator.nlib').mkdir()
        (design / 'initial_floorplan.def').write_text('DEF')
        inputs = {'netlist': str(netlist), 'inputs': {str(netlist): sha(netlist)}}
        summary = {'status': SUCCESS, 'inputs_unchanged': True, 'libraries': {}}
        for label in ('rvt', 'private', 'import'):
            stage = design if label == 'import' else root / ('library_' + label)
            stage.mkdir(exist_ok=True)
            log = stage / 'native.log'
            log.write_text('native completed')
            native_result = SUCCESS if label == 'import' else 'REFERENCE_LIBRARY_CREATED_REVIEW_PENDING'
            status = {'RESULT': [native_result], 'PRIVATE_MACROS': ['56'], 'UNBOUND_CELLS': ['0']}
            value = {'success': True, 'native_status': status,
                     'run': {'status': 'EXIT_0', 'exit_code': 0, 'log': str(log), 'log_sha256': sha(log)}}
            if label == 'import':
                value.update(design_library=str(design / 'accelerator.nlib'), floorplan_def=str(design / 'initial_floorplan.def'))
                summary['import'] = value
            else:
                value['workspace_check_evidence'] = {'accepted': True}
                summary['libraries'][label] = value
        (root / 'PrInputs.json').write_text(json.dumps(inputs))
        (root / 'PrSummary.json').write_text(json.dumps(summary))
        return inputs, summary

    def test_source_native_log_and_original_input_are_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, summary = self.source_fixture(root)
            with patch('PrCoarse.NETLIST_SHA', sha(Path(inputs['netlist']))), patch('PrCoarse.library_check_evidence', return_value={'accepted': True}):
                verify_source(root)
                Path(summary['libraries']['rvt']['run']['log']).write_text('altered log')
                with self.assertRaisesRegex(ValueError, 'native stage'):
                    verify_source(root)
            Path(inputs['netlist']).write_text('altered netlist')
            with self.assertRaisesRegex(ValueError, 'netlist differs'):
                verify_source(root)

    def test_tcl_uses_isolated_open_block_and_stops_on_native_failure(self):
        # Exercise the actual Tcl body with native command substitutes, not ICC2.
        if not shutil.which('tclsh'):
            self.skipTest('External Tcl available in Linux verification')
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            config = 'set PrDesignLib copied.nlib\nset PrRefLibs {copied_rvt.ndm copied_private.ndm}\nset PrTop top\nset PrExpectedLeaves 56\nset PrDef coarse_floorplan.def\n'
            (stage / 'PrCoarseConfig.tcl').write_text(config)
            mock = r'''
proc exit {code} {error MOCK_EXIT_$code}
proc man {args} {return 1}
proc redirect {file script} {
    uplevel 1 $script
    set f [open $file w]
    if {[lindex $script 0] eq "man"} {puts $f "SYNTAX -ref_libs -max_cores -floorplan -effort -hard_macro_overlap -hierarchical -filter"}
    if {[lindex $script 0] eq "report_placement"} {puts $f "Total hard macro to hard macro overlaps: 0"}
    close $f
}
foreach name {open_lib set_ref_libs open_block link_block set_host_options report_placement save_block save_lib report_design report_units} {
    proc $name {args} {return 1}
}
proc create_placement {args} {return $::PlacementReturn}
proc current_block {} {return top}
proc get_cells {args} {
    if {[string first is_unbound $args] >= 0} {return {}}
    set result {}; for {set n 0} {$n<56} {incr n} {lappend result m$n}; return $result
}
proc sizeof_collection {cells} {return [llength $cells]}
proc foreach_in_collection {var collection body} {uplevel 1 [list foreach $var $collection $body]}
proc get_object_name {cell} {return $cell}
proc get_attribute {object attr} {
    if {$attr eq "ref_name"} {return RAMSP1024X16}
    if {$attr eq "core_area_bbox"} {return {{0 0} {1000 1000}}}
    if {$attr eq "bbox"} {return {{0 0} {100 91.485247}}}
    error "Unexpected attribute $attr"
}
proc write_def {file} {set f [open $file w]; puts $f fixture; close $f; return 1}
'''
            for returned, expected in (('1', 'MOCK_EXIT_0'), ('0', 'MOCK_EXIT_2')):
                status = stage / 'PrStatus.tsv'
                if status.exists():
                    status.unlink()
                driver = mock + '\nset PlacementReturn ' + returned + '\ncatch {source [lindex $argv 0]} why\nputs $why\n'
                (stage / 'Driver.tcl').write_text(driver)
                run = subprocess.run(['tclsh', str(stage / 'Driver.tcl'), str(HERE / 'PrCoarse.tcl')], cwd=stage,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
                self.assertIn(expected, run.stdout.decode(), run.stdout.decode())
                if returned == '1':
                    self.assertIn('LOGICAL_LEAF_SIGNATURE\tUNCHANGED', status.read_text())
                else:
                    self.assertNotIn('COARSE_PLACEMENT_NATIVE_COMPLETE', status.read_text())


if __name__ == '__main__':
    unittest.main()
