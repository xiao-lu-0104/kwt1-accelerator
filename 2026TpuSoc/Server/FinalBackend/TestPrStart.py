"""PR orchestration tests only; no local foundry/ICC2 implementation is implied."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from PrStart import select_physical, pg_names, stage_result, verified_formal, scalar, finish, library_check_evidence
from Formal import TOP, read_status
from Preflight import sha
from LefVariants import compare, non_antenna_tokens

HERE = Path(__file__).resolve().parent
MOCK = r'''
proc exit {code} {error "MOCK_EXIT_$code"}
proc man {name} {return 1}
proc redirect {file script} {
    set value [uplevel 1 $script]
    set f [open $file w]
    if {[lindex $script 0] eq "man"} {
        puts $f "SYNTAX $::ManualOptions"
    } elseif {[string first check_workspace $script] >= 0} {
        puts $f $::CheckReport
    } elseif {[lindex $script 0] eq "report_design_mismatch"} {
        puts $f $::MismatchReport
    } else {puts $f "MOCK_NATIVE_REPORT $script"}
    close $f
    return $value
}
proc create_workspace {args} {return 1}
proc set_current_mismatch_config {name} {return 1}
proc get_current_mismatch_config {} {return $::Mismatch}
proc read_db {args} {return 1}
proc read_lef {args} {return 1}
proc check_workspace {} {return $::Check}
proc commit_workspace {args} {
    if {$::Check ni {"" 1} || $::Mismatch ne "default"} {error "Invalid workspace committed"}
    file mkdir [lindex $args end]
    return 1
}
proc create_lib {name args} {file mkdir $name; return 1}
proc read_verilog {args} {return 1}
proc link_block {} {return $::Link}
proc get_cells {args} {
    set filter [lindex $args end]
    if {[string first is_unbound $filter] >= 0} {return $::Unbound}
    if {[string first ref_name $filter] >= 0} {return $::Macros}
    return $::Leaves
}
proc sizeof_collection {collection} {return $collection}
proc create_mode {args} {return 1}
proc create_corner {args} {return 1}
proc create_scenario {args} {return 1}
proc current_scenario {args} {return 1}
proc read_sdc {args} {return 1}
proc create_net {args} {return 1}
proc get_pins {args} {return $::Pins}
proc connect_pg_net {args} {return 1}
proc initialize_floorplan {args} {return 1}
proc save_block {} {return 1}
proc save_lib {} {return 1}
proc write_def {path} {
    set f [open $path w]; puts $f "VERSION 5.8 ; MOCK_DEF"; close $f
    return 1
}
foreach name {report_workspace report_design_mismatch report_design report_units check_design} {
    proc $name {args} {return 1}
}
'''


class PrTests(unittest.TestCase):
    def fixture(self, root):
        std = root / 'SCC40NLL_RVT_V0p1'
        db = std / 'liberty/1.1v/std.db'
        db.parent.mkdir(parents=True)
        db.write_bytes(b'library')
        geometry = std / 'lef/cells.lef'
        tech = std / 'astro/tf/scc40nll_vhs_8lm_1tm.tf'
        tech_lef = std / 'lef/tf/scc40nll_8lm_1tm.lef'
        macro = root / 'ram.lef'
        for path in (geometry, tech, tech_lef, macro):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture', encoding='utf-8')
        netlist = root / 'candidate.v'
        netlist.write_text('module top(input c);\n BUF u(.A(c));\n RAMSP1024X16 m(.CLK(c));\nendmodule\n', encoding='utf-8')
        record = {'assets': [{'kind': 'TECH_OR_RC_CANDIDATE', 'path': str(tech)},
                            {'kind': 'PHYSICAL_DB_DIRECTORY_CANDIDATE', 'path': str(root / '3p3V_io.ndm')}],
                  'physical': {'lef_definitions': {'BUF': [str(geometry)], 'RAMSP1024X16': [str(macro)]},
                               'technology_lef_candidates': [str(tech_lef)]}}
        return db, netlist, record, tech

    def test_selects_matching_rvt_stack_and_never_reuses_io_ndm(self):
        with tempfile.TemporaryDirectory() as directory:
            db, netlist, record, tech = self.fixture(Path(directory))
            result = select_physical(record, db, netlist)
            self.assertEqual(result['technology'], str(tech))
            self.assertFalse(result['existing_io_ndm_used'])
            self.assertEqual(result['used_std_refs'], ['BUF'])
            self.assertIn('NOT_VALIDATED', result['rc_status'])
            record['assets'].append({'kind': 'TECH_OR_RC_CANDIDATE',
                'path': str(Path(directory) / 'HVT/astro/scc40nll_vhs_8lm_1tm.tf')})
            self.assertEqual(select_physical(record, db, netlist)['technology'], str(tech))
            record['physical']['lef_definitions']['BUF'] = []
            with self.assertRaisesRegex(ValueError, 'covering every'):
                select_physical(record, db, netlist)

    def test_missing_or_ambiguous_technology_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            db, netlist, record, tech = self.fixture(Path(directory))
            record['assets'].append({'kind': 'TECH_OR_RC_CANDIDATE', 'path': str(tech.parent / 'alternate' / tech.name)})
            with self.assertRaisesRegex(ValueError, 'TF: expected one'):
                select_physical(record, db, netlist)
            record['assets'] = []
            with self.assertRaisesRegex(ValueError, 'TF: expected one'):
                select_physical(record, db, netlist)

    def test_exact_plain_antenna_pair_requires_content_review_and_unrelated_duplicates_still_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            db, netlist, record, _ = self.fixture(Path(directory))
            plain = Path(record['physical']['lef_definitions']['BUF'][0])
            enhanced = plain.with_name(plain.stem + '_ant.lef')
            record['physical']['lef_definitions']['BUF'].append(str(enhanced))
            selected = select_physical(record, db, netlist)
            self.assertEqual(selected['std_lef'], str(enhanced))
            self.assertEqual(selected['std_lef_variant']['status'], 'CONTENT_CHECK_REQUIRED')
            record['physical']['lef_definitions']['BUF'].append(str(plain.with_name('other.lef')))
            with self.assertRaisesRegex(ValueError, 'covering every'):
                select_physical(record, db, netlist)

    def test_antenna_pair_requires_identical_remaining_tokens_and_old_hashes(self):
        plain_text = '''VERSION 5.8 ;
MACRO BUF
 CLASS CORE ;
 SIZE 1.2 BY 2.4 ;
 SITE core ;
 PIN A
  DIRECTION INPUT ;
  USE SIGNAL ;
  PORT
   LAYER M1 ;
   RECT 0 0 0.1 0.2 ;
  END
 END A
 OBS
  LAYER M2 ;
  RECT 0 0 0.1 0.2 ;
 END
END BUF
END LIBRARY
'''
        extra = '  ANTENNAMODEL OXIDE1 ;\n  ANTENNAGATEAREA 0.3 LAYER M1 ;\n  ANTENNAPARTIALMETALAREA\n   0.8 LAYER M1 ;\n'
        with tempfile.TemporaryDirectory() as directory:
            regular, enhanced = Path(directory) / 'cells.lef', Path(directory) / 'cells_ant.lef'
            regular.write_text(plain_text, encoding='utf-8')
            enhanced.write_text(plain_text.replace('  USE SIGNAL ;', '  USE SIGNAL ;\n' + extra), encoding='utf-8')
            result = compare(regular, enhanced, sha(regular), sha(enhanced))
            self.assertEqual(result['status'], 'NON_ANTENNA_TOKENS_IDENTICAL')
            self.assertEqual(result['enhanced_antenna_statements']['ANTENNAGATEAREA'], 1)
            for changed in ('SIZE 1.3 BY 2.4', 'RECT 0 0 0.9 0.2', 'LAYER M3', 'USE POWER'):
                if changed.startswith('SIZE'):
                    text = enhanced.read_text().replace('SIZE 1.2 BY 2.4', changed)
                elif changed.startswith('RECT'):
                    text = enhanced.read_text().replace('RECT 0 0 0.1 0.2', changed)
                elif changed.startswith('LAYER'):
                    text = enhanced.read_text().replace('LAYER M2', changed)
                else:
                    text = enhanced.read_text().replace('USE SIGNAL', changed)
                enhanced.write_text(text, encoding='utf-8')
                self.assertEqual(compare(regular, enhanced, sha(regular), sha(enhanced))['status'], 'REJECTED_NON_ANTENNA_DIFFERENCE')
                enhanced.write_text(plain_text.replace('  USE SIGNAL ;', '  USE SIGNAL ;\n' + extra), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'previously inspected SHA'):
                compare(regular, enhanced, '0' * 64, sha(enhanced))

    def test_antenna_normalizer_does_not_hide_names_strings_or_malformed_statements(self):
        text = '''MACRO ANTENNAGATEAREA
 SIZE 1 BY 2 ;
 PIN ANTENNADIFFAREA
  PROPERTY note "ANTENNAGATEAREA # ;" ;
  DIRECTION INPUT ;
 END ANTENNADIFFAREA
END ANTENNAGATEAREA
'''
        kept, dropped = non_antenna_tokens(text)
        self.assertEqual(dropped, {})
        self.assertIn('"ANTENNAGATEAREA # ;"', kept)
        self.assertIn('ANTENNADIFFAREA', kept)
        malformed = 'MACRO BUF\nPIN A\nANTENNAGATEAREA 0.3\nRECT 0 0 1 1 ;\nEND A\nEND BUF\n'
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            non_antenna_tokens(malformed)
        unknown = 'MACRO BUF\nPIN A\nANTENNA_UNKNOWN 1 ;\nEND A\nEND BUF\n'
        self.assertIn('ANTENNA_UNKNOWN', non_antenna_tokens(unknown)[0])

    def test_variant_worker_retains_json_and_nonzero_status_for_real_geometry_difference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular, enhanced = root / 'cells.lef', root / 'cells_ant.lef'
            output = root / 'review.json'
            text = 'MACRO BUF\n SIZE 1 BY 2 ;\n PIN A\n USE SIGNAL ;\n END A\nEND BUF\n'
            regular.write_text(text, encoding='utf-8')
            enhanced.write_text(text.replace(' USE SIGNAL ;', ' USE SIGNAL ;\n ANTENNAGATEAREA 0.3 ;'), encoding='utf-8')
            def run():
                return subprocess.run([sys.executable, '-B', str(HERE / 'LefVariants.py'),
                    '--regular', str(regular), '--antenna', str(enhanced),
                    '--regular-sha', sha(regular), '--antenna-sha', sha(enhanced), '--output', str(output)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            self.assertEqual(run().returncode, 0)
            self.assertEqual(json.loads(output.read_text())['status'], 'NON_ANTENNA_TOKENS_IDENTICAL')
            enhanced.write_text(enhanced.read_text().replace('SIZE 1 BY 2', 'SIZE 2 BY 2'), encoding='utf-8')
            self.assertEqual(run().returncode, 2)
            proof = json.loads(output.read_text())
            self.assertEqual(proof['status'], 'REJECTED_NON_ANTENNA_DIFFERENCE')
            self.assertIn('first_difference_index', proof)

    def test_pg_mapping_requires_explicit_supported_single_voltage_pins(self):
        std = {'macros': {'BUF': {'pins': {'VDD': {'use': 'POWER'}, 'VSS': {'use': 'GROUND'}}}}}
        ram = {'macros': {'RAMSP1024X16': {'pins': {'VDDCE': {'use': 'POWER'}, 'VDDPE': {'use': 'POWER'}, 'VSSE': {'use': 'GROUND'}}}}}
        power, ground = pg_names(std, ram, ['BUF'])
        self.assertEqual(power, ['VDD', 'VDDCE', 'VDDPE'])
        self.assertEqual(ground, ['VSS', 'VSSE'])
        std['macros']['BUF']['pins']['VBB'] = {'use': 'POWER'}
        with self.assertRaisesRegex(ValueError, 'mapping needs review'):
            pg_names(std, ram, ['BUF'])
        del std['macros']['BUF']['pins']['VBB']
        del std['macros']['BUF']['pins']['VSS']
        with self.assertRaisesRegex(ValueError, 'lacks explicit'):
            pg_names(std, ram, ['BUF'])

    def test_exit_zero_without_native_success_or_with_error_or_missing_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'native.log'
            log.write_text('normal', encoding='utf-8')
            run = {'exit_code': 0, 'status': 'EXIT_0', 'log': str(log)}
            status = {'RESULT': ['DONE']}
            self.assertTrue(stage_result(run, status, 'DONE')['success'])
            self.assertFalse(stage_result(run, {}, 'DONE')['success'])
            self.assertFalse(stage_result(run, status, 'DONE', [root / 'missing.ndm'])['success'])
            log.write_text('Error: library mismatch', encoding='utf-8')
            self.assertFalse(stage_result(run, status, 'DONE')['success'])

    def test_formal_success_is_bound_to_native_log_and_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            netlist = root / 'candidate.v'
            netlist.write_bytes(b'frozen')
            log = root / 'fm_actual.log'
            log.write_text('native verification success fixture', encoding='utf-8')
            inputs = {'top': TOP, 'inputs': {str(netlist): sha(netlist)}, 'implementation_netlist': str(netlist)}
            summary = {'status': 'TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING', 'frozen_candidate_unchanged': True,
                       'native_status': {k: ['1'] for k in ('GUIDANCE_READ_RETURN', 'MATCH_RETURN', 'VERIFY_RETURN')},
                       'run': {'exit_code': 0, 'status': 'EXIT_0', 'log_sha256': sha(log)}}
            (root / 'FormalInputs.json').write_text(json.dumps(inputs), encoding='utf-8')
            proof = root / 'FormalSummary.json'
            proof.write_text(json.dumps(summary), encoding='utf-8')
            with patch('PrStart.NETLIST_SHA', sha(netlist)):
                verified_formal(root)
                log.write_text('changed log', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'verify=1'):
                    verified_formal(root)
                log.write_text('native verification success fixture', encoding='utf-8')
                netlist.write_bytes(b'changed netlist')
                with self.assertRaisesRegex(ValueError, 'input changed'):
                    verified_formal(root)

    def run_tcl(self, kind, overrides=None):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            values = {'Mismatch': 'default', 'Check': '1', 'Link': '1', 'Unbound': '0', 'Macros': '56',
                      'Leaves': '71809', 'Pins': '56',
                      'CheckReport': 'Warning: M1 routing obstruction (FRAM-066)\n... created 1276 frames\nWorkspace check succeeded!',
                      'MismatchReport': 'Report : Data Mismatches\nNo mismatches exist on the design.\n1',
                      'ManualOptions': '-technology -output -ref_libs -top -hierarchical -filter -name -mode -corner -power -ground -physical_context -net -core_utilization -core_offset'}
            values.update(overrides or {})
            if kind == 'Library':
                config = 'set PrTechnology fixture.tf\nset PrWorkspace rvt\nset PrDb fixture.db\nset PrLefs {fixture.lef}\nset PrNdm rvt.ndm\n'
            else:
                config = 'set PrTechnology fixture.tf\nset PrDesignLib accelerator.nlib\nset PrTop top\nset PrNetlist fixture.v\nset PrSdc fixture.sdc\nset PrDef initial.def\nset PrRefLibs {rvt.ndm private.ndm}\nset PrPowerPins {VDD VDDCE VDDPE}\nset PrGroundPins {VSS VSSE}\n'
            (out / ('Pr' + kind + 'Config.tcl')).write_text(config, encoding='utf-8')
            driver = MOCK
            for name, value in values.items():
                if name in ('CheckReport', 'MismatchReport'):
                    driver += '\nset ' + name + ' [encoding convertfrom utf-8 [binary format H* ' + value.encode().hex() + ']]\n'
                else:
                    driver += '\n' + scalar(name, value)
            script = HERE / ('Pr' + kind + '.tcl')
            external = shutil.which('tclsh')
            if external:
                driver += '\ncatch {source [lindex $argv 0]} why\nset f [open MockExit.txt w]\nputs $f $why\nclose $f\n'
                (out / 'Driver.tcl').write_text(driver, encoding='utf-8')
                run = subprocess.run([external, str(out / 'Driver.tcl'), str(script)], cwd=out,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
                self.assertEqual(run.returncode, 0, run.stdout.decode(errors='replace'))
                code = (out / 'MockExit.txt').read_text().strip()
            else:
                import tkinter
                interp = tkinter.Tcl()
                previous = os.getcwd()
                interp.call('cd', out.as_posix())
                try:
                    interp.eval(driver)
                    with self.assertRaises(tkinter.TclError) as error:
                        interp.call('source', script.as_posix())
                    code = str(error.exception)
                finally:
                    interp.call('cd', Path(previous).as_posix())
            return code, read_status(out / 'PrStatus.tsv'), (out / 'initial.def').exists(), (out / 'rvt.ndm').exists()

    def test_library_requires_native_success_and_zero_mismatches_with_empty_or_true_return(self):
        for value in ('', '1'):
            code, status, _, ndm = self.run_tcl('Library', {'Check': value})
            self.assertEqual(code, 'MOCK_EXIT_0')
            self.assertEqual(status['CHECK_WORKSPACE_RETURN'], [value])
            self.assertEqual(status['CHECK_WORKSPACE_ACCEPTED'], ['1'])
            self.assertTrue(ndm)
        for values in ({'Check': '0'}, {'Check': 'unexpected'}, {'Mismatch': 'auto_fix'},
                       {'Check': '', 'CheckReport': 'Only information; no final result'},
                       {'CheckReport': 'Workspace check failed!'},
                       {'CheckReport': 'Error: bad library\nWorkspace check succeeded!'},
                       {'MismatchReport': 'One mismatch exists.'},
                       {'MismatchReport': 'Fatal: bad\nNo mismatches exist on the design.'}):
            code, status, _, ndm = self.run_tcl('Library', values)
            self.assertEqual(code, 'MOCK_EXIT_2')
            self.assertFalse(ndm)
            self.assertEqual(status['RESULT'], ['REFERENCE_LIBRARY_FAILED'])

    def test_python_rechecks_native_library_reports_instead_of_trusting_status(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            status = {'MISMATCH_POLICY': ['default'], 'CHECK_WORKSPACE_RETURN': [''],
                      'CHECK_WORKSPACE_ACCEPTED': ['1'],
                      'CHECK_WORKSPACE_EVIDENCE': ['NATIVE_SUCCESS_AND_NO_DESIGN_MISMATCHES']}
            check = stage / 'check_workspace.rpt'
            mismatch = stage / 'report_design_mismatch.rpt'
            self.assertFalse(library_check_evidence(stage, status)['accepted'])
            check.write_text('Warning: large M1 blockage (FRAM-066)\nWorkspace check succeeded!\n')
            mismatch.write_text('No mismatches exist on the design.\n1\n')
            evidence = library_check_evidence(stage, status)
            self.assertTrue(evidence['accepted'])
            self.assertEqual(evidence['fram_066_warning_count'], 1)
            self.assertEqual(evidence['report_sha256']['check_workspace.rpt'], sha(check))
            for text in ('No result', 'Workspace check failed!', 'Error: bad\nWorkspace check succeeded!'):
                check.write_text(text)
                self.assertFalse(library_check_evidence(stage, status)['accepted'])
            check.write_text('Workspace check succeeded!')
            mismatch.write_text('Mismatches found')
            self.assertFalse(library_check_evidence(stage, status)['accepted'])
            mismatch.write_text('No mismatches exist on the design.')
            for key, value in (('MISMATCH_POLICY', ['auto_fix']), ('CHECK_WORKSPACE_RETURN', ['0']),
                               ('CHECK_WORKSPACE_RETURN', ['unknown']), ('CHECK_WORKSPACE_ACCEPTED', ['0'])):
                changed = dict(status)
                changed[key] = value
                self.assertFalse(library_check_evidence(stage, changed)['accepted'])

    def test_import_requires_real_link_zero_unbound_56_macros_and_nonempty_def(self):
        code, status, definition, _ = self.run_tcl('Import')
        self.assertEqual(code, 'MOCK_EXIT_0')
        self.assertTrue(definition)
        self.assertEqual(status['PRIVATE_MACROS'], ['56'])
        for values in ({'Link': '0'}, {'Unbound': '1'}, {'Macros': '55'}, {'Leaves': '60'}, {'Pins': '0'}):
            code, status, definition, _ = self.run_tcl('Import', values)
            self.assertEqual(code, 'MOCK_EXIT_2')
            self.assertFalse(definition)
            self.assertEqual(status['RESULT'], ['ICC2_IMPORT_OR_FLOORPLAN_FAILED'])

    def test_installed_manual_must_confirm_options_before_mutation(self):
        code, status, definition, _ = self.run_tcl('Import', {'ManualOptions': '-technology'})
        self.assertEqual(code, 'MOCK_EXIT_2')
        self.assertFalse(definition)
        self.assertIn('does not confirm -ref_libs', status['ERROR'][0])

    def test_failed_preparation_still_archives_diagnostics_without_copying_ndm_or_claiming_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'reference.ndm').mkdir()
            (out / 'reference.ndm/private.txt').write_text('not in report package', encoding='utf-8')
            (out / 'selection.json').write_text('{}', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                finish(out, {}, {}, None, 'fixture preparation failure')
            summary = json.loads((out / 'PrSummary.json').read_text(encoding='utf-8'))
            self.assertIsNone(summary['inputs_unchanged'])
            self.assertEqual(summary['status'], 'ICC2_START_INCOMPLETE_REVIEW_LOGS')
            with tarfile.open(out / 'PrStartReports.partial.tar.gz') as stream:
                self.assertFalse(any('private.txt' in name for name in stream.getnames()))
                self.assertTrue(any('selection.json' in name for name in stream.getnames()))


if __name__ == '__main__':
    unittest.main()
