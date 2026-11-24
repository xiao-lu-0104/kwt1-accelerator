"""Exercise retained violations, checkpoint recovery and actual Tcl stage dispatch."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from BuildContinuePr import build_files
from BuildFastEngineeringPr import build_tcl

HERE = Path(__file__).resolve().parent


def load(root):
    for name, data in build_files().items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root/'tools/FastEngineeringPr.tcl').write_text(build_tcl())
    sys.path.insert(0, str(root/'tools'))
    spec = importlib.util.spec_from_file_location('FastFixture', HERE/'FastEngineeringPr.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Tests(unittest.TestCase):
    def test_elapsed_budget_does_not_terminate_unsaved_native_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = load(root)
            library = root/'source.nlib'
            library.mkdir()
            (library/'db').write_text('saved source')

            class Native:
                pid = 45678

                def __init__(self, command, cwd, stdout, **kwargs):
                    self.calls = 0
                    stdout.write('CONTINUE_CORE_SAVED: fixture\nCONTINUE_PHASE_COMPLETE: fixture\n')

                def wait(self, timeout=None):
                    self.calls += 1
                    if self.calls == 1:
                        raise subprocess.TimeoutExpired('fixture', 60)
                    return 0

            record = {'reference_libraries': [], 'variables': {}, 'icc2': 'fixture', 'icc2_flag': '-file'}
            with patch.object(module.subprocess, 'Popen', Native), \
                 patch.object(module.time, 'monotonic', side_effect=[0, 1000, 1001]):
                result = module.run_stage(root, record, 'fixture', 'fixture', library, 1)
            self.assertTrue(result['complete'])
            self.assertEqual(result['native_exit'], 0)

    def test_quality_violations_continue_and_native_failure_resumes_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = load(root)
            home = root/'home'
            source = home/'soc/initial'
            (source/'inputs').mkdir(parents=True)
            (source/'design/system_707cd7f.nlib').mkdir(parents=True)
            (source/'design/system_707cd7f.nlib/db').write_text('original placement')
            for name in ('inputs/candidate.v', 'inputs/candidate.sdc', 'design/PinPlan.json',
                         'design/IoValidation.json', 'design/PortTerminalGeometry.tsv'):
                (source/name).write_text('fixture '+name)
            refs = {}
            for label in ('rvt', 'private', 'shared'):
                ref = source/('library_'+label)/(label+'.ndm')
                ref.mkdir(parents=True)
                (ref/'db').write_text(label)
                refs[str(ref)] = module.snapshot(ref)
            inputs = {'source_commit': module.REV, 'inputs': {}, 'reference_snapshots': refs,
                      'design_sdc_sha256': module.sha(source/'inputs/candidate.sdc'),
                      'expected_serialized_period_ns': '6.66667'}
            summary = {'design_netlist_sha256': module.sha(source/'inputs/candidate.v')}
            (source/'NewPrInputs.json').write_text(json.dumps(inputs))
            (source/'NewPrSummary.json').write_text(json.dumps(summary))
            origin = root/'origin'
            (origin/'stages/01_rc').mkdir(parents=True)
            (origin/'Config.json').write_text(json.dumps({'initial_package_sha256': 'fixture'}))
            variables = {}
            for name in ('BaselineLeaves', 'BaselineMacros', 'RcTlu', 'RcMap'):
                path = root/name
                path.write_text('fixture '+name)
                variables[name] = path
            variables['BaselineIo'] = source/'design/PortTerminalGeometry.tsv'
            (origin/'stages/01_rc/ContinueConfig.tcl').write_text(''.join(module.scalar(k, v) for k, v in variables.items()))
            (origin/'ContinueInputs.json').write_text(json.dumps({'original_files': {}}))
            physical = home/'soc/tpusoc_icc2_start_20261108_mTq1LE'
            physical.mkdir()
            (physical/'PrInputs.json').write_text(json.dumps({'icc2': 'fixture', 'icc2_flag': '-file'}))
            out = root/'output'
            out.mkdir()
            actions = []
            fail = {'enabled': True}

            class Native:
                pid = 12345

                def __init__(self, command, cwd, stdout, **kwargs):
                    directory = Path(cwd)
                    self.code = 0
                    action = re.search(r'set Action \{([^}]+)\}', (directory/'ContinueConfig.tcl').read_text()).group(1)
                    actions.append(action)
                    if action == '04_route_clock' and fail['enabled']:
                        fail['enabled'] = False
                        self.code = 2
                        stdout.write('CONTINUE_NATIVE_ERROR: fixture operational failure\n')
                        return
                    if action == 'connectivity':
                        report = '\n'.join('Verify net '+net+' connectivity\nNumber of floating wires: 8\nNumber of floating vias: 0\nNumber of floating std cells: 6\nNumber of floating hard macros: 120' for net in ('VDD', 'VSS'))
                        (directory/'connectivity.rpt').write_text(report)
                    elif action == 'drc':
                        (directory/'drc.rpt').write_text('Total number of errors found: 17\n17 insufficient spacings on M4\n')
                    else:
                        (directory/'checkpoint.def').write_text('NETS 150 ;\n'+''.join('- net%d + ROUTED M3 ( 0 0 ) ;\n'%i for i in range(150))+'END NETS\n')
                        for name in ('routed.v', 'routed.sdc', 'setup.rpt', 'hold.rpt', 'route_check.rpt'):
                            (directory/name).write_text('slack (VIOLATED) -0.250\nTotal number of DRCs = 939\n')
                        stdout.write('CONTINUE_CORE_SAVED: '+action+'\n')
                    stdout.write('CONTINUE_PHASE_COMPLETE: '+action+'\n')

                def wait(self, timeout=None):
                    return self.code

            with patch.object(module, 'ORIGIN', origin), patch.object(module.Path, 'home', return_value=home), \
                 patch.object(module, 'choose_source', return_value=(source, summary)), \
                 patch.object(module.subprocess, 'Popen', Native):
                with self.assertRaisesRegex(ValueError, 'Native stage failed'):
                    module.main(out)
                progress = json.loads((out/'FastPrProgress.json').read_text())
                self.assertIn('04_build_clock', progress['last_successful_library'])
                module.main(out)
            result = json.loads((out/'FastPrSummary.json').read_text())
            self.assertFalse(result['checks']['connectivity']['clean'])
            self.assertEqual(result['checks']['drc']['total'], 17)
            self.assertEqual(result['ordinary_net_route_records'], 150)
            self.assertEqual(actions.count('02_pg_basic'), 1)
            self.assertEqual(actions.count('04_build_clock'), 1)
            self.assertEqual(actions.count('04_route_clock'), 2)
            self.assertTrue((out/'OpenRoutedLayout.tcl').is_file())
            self.assertTrue((out/'ImplementationReport.md').is_file())
            self.assertTrue((out/'FastPrReports.tar.gz').is_file())
            self.assertEqual((source/'design/system_707cd7f.nlib/db').read_text(), 'original placement')

    def test_actual_tcl_stages_save_and_use_split_cts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            load(root)
            prefix = (HERE/'TestPgStage.tcl').read_text().split('if {$Kind in {connectivity drc}}', 1)[0]
            test = (HERE/'TestContinuePr.py').read_text()
            suffix = test.split("suffix=r'''", 1)[1].split("'''\n            harness=", 1)[0]
            extra = '''
proc create_pg_mesh_pattern args {
    if {[regexp -all {pitch: 84} $args]!=3 || [regexp -all {pitch: 168} $args]!=1} {error "Unexpected sparse mesh"}
    return 1
}
proc create_pg_macro_conn_pattern args {set ::LongPin 1;return 1}
proc man args {puts {SYNTAX build_clock route_clock -from -to -max_detail_route_iterations -ref_libs -max_cores -type -outer -horizontal_layer -vertical_layer -horizontal_width -vertical_width -horizontal_spacing -vertical_spacing -layers -pin_conn_type -direction -pin_layers -width -spacing -pitch -via_rule -core -macros -pattern -extension -blockage -via_array_dimension -strategies -name -value -output -tlup -layermap -sanity_check -corners -early_spec -late_spec -early_temperature -late_temperature -check_macro_pins -check_std_cell_pins}}
proc clock_opt args {
    if {$args ni {{-from build_clock -to build_clock} {-from route_clock -to route_clock}}} {error "Unexpected full clock optimization"}
    return 1
}
'''
            suffix = suffix.replace('source [file join $Tools ContinuePr.tcl]', extra+'\nsource [file join $Tools FastEngineeringPr.tcl]')
            harness = root/'Harness.tcl'
            harness.write_text(prefix+suffix)
            for action in ('01_rc', '02_pg_basic', '04_build_clock', '04_route_clock', '05_route', '07_export', 'connectivity', 'drc'):
                out = root/action
                result = subprocess.run(['tclsh', str(harness), str(root/'tools'), str(out), action, ''],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                self.assertEqual(result.returncode, 0, action+'\n'+result.stdout+result.stderr)
                self.assertIn('CONTINUE_PHASE_COMPLETE: '+action, result.stdout)
                if action not in ('connectivity', 'drc'):
                    self.assertTrue((out/'checkpoint.def').is_file())


if __name__ == '__main__':
    unittest.main()
