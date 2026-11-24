"""Inventory must distinguish physical evidence from file presence and protect inputs."""
import gzip
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'SystemBackend'))
from InitialMaterials import write_manifest
from Preflight import sha, lef_info, scan_assets, inspect_assets, structural_references, load_candidate, command, tools_inventory, physical_inventory, validate_resume, recovered_log

LEF = '''VERSION 5.8 ;
LAYER M1
 TYPE ROUTING ;
 DIRECTION HORIZONTAL ;
END M1
SITE core_site
 CLASS CORE ;
 SIZE 0.2 BY 1.8 ;
END core_site
MACRO RAMSP4096X16
 CLASS BLOCK ;
 SIZE 120 BY 240 ;
 PIN CLK
  DIRECTION INPUT ;
  USE SIGNAL ;
 END CLK
 PIN VDCE
  DIRECTION INOUT ;
  USE POWER ;
 END VDCE
 PIN VSSE
  DIRECTION INOUT ;
  USE GROUND ;
 END VSSE
END RAMSP4096X16
MACRO BUF
 CLASS CORE ;
 SIZE .2 BY 1.8 ;
 SITE core_site ;
END BUF
'''


def fixture(base):
    source = base / 'source'
    root = source / 'InitialMaterials'
    (root / 'Project/Rtl').mkdir(parents=True)
    (root / 'Backend').mkdir()
    power = base / 'power'
    task = base / 'task'
    system = base / 'system'
    for path in (power, task, system / 'mapped'):
        path.mkdir(parents=True)
    netlist = system / 'mapped/candidate.v'
    netlist.write_text('module leaf(input a); BUF b(.A(a)); endmodule\n'
                       'module e203_cpu_top(input clk);\n RAMSP1024X16 r0(.CLK(clk));\n'
                       ' RAMSP4096X16 r1(.CLK(clk));\n BUF b(.A(clk));\n leaf h(.a(clk));\nendmodule\n', encoding='utf-8')
    backend = root / 'Backend/BackendRawMaterials.partial.tar.gz'
    with tarfile.open(backend, 'w:gz') as stream:
        data = netlist.read_bytes()
        info = tarfile.TarInfo('BackendRawMaterials/Netlist/candidate.v')
        info.size = len(data)
        stream.addfile(info, io.BytesIO(data))
    paths = {}
    inputs = {}
    for name in ('ddc', 'sdc', 'std_db', 'private_db', 'shared_db'):
        path = base / (name + '.data')
        path.write_text('FROZEN ' + name, encoding='utf-8')
        paths[name], inputs[str(path)] = str(path), sha(path)
    (power / 'Inputs.json').write_text(json.dumps({'paths': paths, 'inputs': inputs}), encoding='utf-8')
    (task / 'Inputs.json').write_text(json.dumps({'source': str(system)}), encoding='utf-8')
    record = {'numerical_replay': 'PASS_FIXED_POINT_HEX_REPLAY',
              'float_parameter_sha256': {str(index): 'FIXTURE' for index in range(37)},
              'backend_results': {'power_source': str(power), 'task_source': str(task)}}
    (root / 'ReviewStatus.json').write_text(json.dumps(record), encoding='utf-8')
    write_manifest(root)
    archive = source / 'InitialMaterials.candidate.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        for path in root.rglob('*'):
            if path.is_file():
                stream.add(path, arcname='InitialMaterials/' + path.relative_to(root).as_posix())
    out = base / 'out'
    out.mkdir()
    return source, out, sha(archive)


class PreflightTests(unittest.TestCase):
    def test_lef_routes_sites_and_macro_pg_pins_are_kept_separate(self):
        details = lef_info(LEF)
        self.assertEqual(details['routing_layers'], ['M1'])
        self.assertEqual(details['sites'], ['core_site'])
        self.assertEqual(details['macros']['RAMSP4096X16']['pins']['VDCE']['use'], 'POWER')
        self.assertEqual(details['macros']['RAMSP4096X16']['pins']['VSSE']['use'], 'GROUND')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.lef.gz'
            # Geometry-only LEF must not be mistaken for a technology layer definition.
            path.write_bytes(gzip.compress(LEF[LEF.index('MACRO'):].encode()))
            result = inspect_assets([{'path': str(path), 'kind': 'LEF'}], {'BUF': 1, 'MISSING': 1})
            self.assertEqual(result['technology_lef_candidates'], [])
            self.assertEqual(result['missing_reference_lef'], ['MISSING'])
            self.assertIn('FILE_INVENTORY_ONLY', result['acceptance'])

    def test_structural_parser_excludes_design_modules_and_keywords(self):
        text = 'module inner(input a); endmodule\nmodule top(input c);\n inner h(.a(c));\n BUF \\u[0] (.A(c));\nendmodule\n'
        self.assertEqual(structural_references(text), {'BUF': 1})

    def test_bounded_scan_records_truncation_without_claiming_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.tf').write_text('TECH', encoding='utf-8')
            (root / 'b.lef').write_text(LEF, encoding='utf-8')
            assets, status = scan_assets([root], max_files=1)
            self.assertTrue(status['truncated'])
            self.assertEqual(len(assets), 1)

    def test_candidate_and_required_checkpoint_fingerprints_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, digest = fixture(Path(directory))
            before = {path: sha(path) for path in source.rglob('*') if path.is_file()}
            root, inputs, result = load_candidate(source, out, digest)
            self.assertEqual(set(result['reference_declarations']), {'BUF', 'RAMSP1024X16', 'RAMSP4096X16'})
            self.assertEqual(result['top'], 'e203_cpu_top')
            for path, value in before.items():
                self.assertEqual(sha(path), value)
            Path(result['paths']['ddc']).write_text('CHANGED', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Frozen tool input changed'):
                load_candidate(source, out, digest)

    @unittest.skipIf(os.name == 'nt', 'POSIX tool process-group supervision')
    def test_help_timeout_is_recorded_without_calling_it_success(self):
        with tempfile.TemporaryDirectory() as directory:
            result = command([sys.executable, '-c', 'import time; time.sleep(30)'], Path(directory), 'timeout', .1)
            self.assertEqual(result['status'], 'TIMEOUT')
            self.assertEqual(result['exit_code'], 124)

    def test_unstartable_tool_does_not_abort_inventory_or_look_successful(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            result = command([str(out / 'missing_tool')], out, 'missing')
            self.assertEqual(result['status'], 'START_ERROR')
            self.assertEqual(result['exit_code'], 127)

    def test_inaccessible_installation_records_unknown_and_checks_remaining_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / 'eda'
            executable = install / 'synopsys/icc2/version/bin/icc2_shell'
            executable.parent.mkdir(parents=True)
            executable.write_text('fixture only', encoding='utf-8')
            executable.chmod(0o755)
            real_glob = Path.glob

            def guarded_glob(path, pattern):
                if path == install / 'cadence/innovus':
                    # Raise during iteration, as the server's Python 3.6 does.
                    def denied():
                        raise PermissionError(13, 'Permission denied', str(path))
                        yield
                    return denied()
                return real_glob(path, pattern)

            with patch('Preflight.shutil.which', return_value=None), \
                 patch.object(Path, 'glob', guarded_glob), \
                 patch('Preflight.command', return_value={'status': 'EXIT_0', 'exit_code': 0}) as run:
                result = tools_inventory(root, install)
            self.assertEqual(result['innovus']['availability'], 'DISCOVERY_INCOMPLETE_ACCESS_ERROR')
            self.assertEqual(result['innovus']['discovery_errors'][0]['errno'], 13)
            self.assertEqual(result['icc2_shell']['executable'], str(executable))
            self.assertEqual(result['dc_shell']['availability'], 'EXECUTABLE_NOT_FOUND_IN_PATH_OR_KNOWN_INSTALLATIONS')
            run.assert_called_once_with([str(executable), '-help'], root, 'icc2_shell_help', 25)

    def test_inaccessible_pdk_root_does_not_hide_accessible_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            denied = root / 'denied'
            (root / 'available.lef').write_text(LEF, encoding='utf-8')
            real_is_dir = Path.is_dir

            def guarded_is_dir(path):
                if path == denied:
                    raise PermissionError(13, 'Permission denied', str(path))
                return real_is_dir(path)

            with patch.object(Path, 'is_dir', guarded_is_dir):
                assets, status = scan_assets([denied, root])
            self.assertEqual(status['errors'][0]['errno'], 13)
            self.assertEqual([item['path'] for item in assets], [str(root / 'available.lef')])

    def test_nested_geometry_layers_and_repeated_macros_do_not_become_technology(self):
        text = LEF + '''MACRO OTHER
 SIZE 1 BY 2 ;
 PIN A
  DIRECTION INPUT ;
  PORT
   LAYER M99 ;
   RECT 0 0 1 1 ;
  END
 END A
END OTHER
'''
        result = lef_info(text)
        self.assertEqual(result['routing_layers'], ['M1'])
        self.assertEqual(result['macros']['OTHER']['size_um'], [1, 2])
        self.assertEqual(result['macros']['OTHER']['pins']['A']['direction'], 'INPUT')

    def test_physical_workers_collect_valid_assets_and_report_invalid_gzip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library, out = root / 'library', root / 'out'
            library.mkdir()
            out.mkdir()
            (library / 'good.lef').write_text(LEF, encoding='utf-8')
            (library / 'broken.lef.gz').write_bytes(b'not gzip')
            assets, scan, physical = physical_inventory(out, [library], {'BUF': 1, 'MISSING': 1})
            self.assertEqual(scan['files_seen'], 2)
            self.assertFalse(scan['truncated'])
            self.assertEqual(physical['missing_reference_lef'], ['MISSING'])
            self.assertTrue(physical['inspection_truncated'])
            self.assertEqual(len(physical['errors']), 1)
            self.assertEqual(physical['sram_lef_details']['RAMSP4096X16'][0]['pins']['VDCE']['use'], 'POWER')

    @unittest.skipIf(os.name == 'nt', 'POSIX worker process-group deadline')
    def test_blocked_lef_read_times_out_and_continues_next_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library, out = root / 'library', root / 'out'
            library.mkdir()
            out.mkdir()
            (library / 'good.lef').write_text(LEF, encoding='utf-8')
            # A FIFO named *.lef reproduces an indefinitely blocked file read.
            os.mkfifo(str(library / 'blocked.lef'))
            assets, scan, physical = physical_inventory(out, [library], {'BUF': 1}, file_limit=.2)
            self.assertEqual(len(assets), 2)
            self.assertFalse(scan['truncated'])
            self.assertEqual(physical['missing_reference_lef'], [])
            self.assertEqual(physical['errors'][0]['error'], 'TIMEOUT')
            self.assertTrue(physical['inspection_truncated'])

    @unittest.skipIf(os.name == 'nt', 'POSIX scan worker process-group deadline')
    def test_blocked_scan_preserves_checkpoint_and_continues_next_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library, out = root / 'library', root / 'out'
            library.mkdir()
            out.mkdir()
            (library / 'good.lef').write_text(LEF, encoding='utf-8')
            script = ('import json,sys,time; from pathlib import Path; '
                      'Path(sys.argv[1]).write_text(json.dumps({"assets": [{"path": "partial.tf", '
                      '"kind": "TECH_OR_RC_CANDIDATE"}], "scan": {"files_seen": 1, "truncated": True, '
                      '"errors": [], "worker_complete": False}})); time.sleep(30)')

            def stalled_scan(argv, folder, label, limit):
                if label == 'pdk_scan_0':
                    argv = [sys.executable, '-c', script, str(out / 'pdk_scan_0.json')]
                    limit = .2
                return command(argv, folder, label, limit)

            with patch('Preflight.command', side_effect=stalled_scan):
                assets, scan, physical = physical_inventory(out, [root / 'stalled', library], {'BUF': 1})
            self.assertTrue(scan['truncated'])
            self.assertEqual(scan['worker_runs'][0]['status'], 'TIMEOUT')
            self.assertIn('partial.tf', physical['tech_or_rc_candidates'])
            self.assertEqual(physical['missing_reference_lef'], [])

    def test_recovered_logs_have_unknown_exit_status_and_inputs_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous, out = root / 'previous', root / 'out'
            (previous / 'tools').mkdir(parents=True)
            out.mkdir()
            script = previous / 'tools/Preflight.py'
            script.write_text('known fixture', encoding='utf-8')
            (previous / 'FrozenInputs.json').write_text('{"same": true}', encoding='utf-8')
            (previous / 'fm_help.log').write_text('previous help', encoding='utf-8')
            with patch('Preflight.RESUME_SCRIPT_SHA256', sha(script)):
                validate_resume(previous, {'same': True})
                with self.assertRaisesRegex(ValueError, 'inputs differ'):
                    validate_resume(previous, {'same': False})
            result = recovered_log(previous, out, 'fm_help')
            self.assertEqual(result['status'], 'RECOVERED_LOG_EXIT_STATUS_UNKNOWN')
            self.assertIsNone(result['exit_code'])
            self.assertEqual(sha(out / 'fm_help.log'), sha(previous / 'fm_help.log'))


if __name__ == '__main__':
    unittest.main()
