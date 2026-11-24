"""New system collector tests with isolated fixture platform and fake EDA."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import SystemFlow as F
from BuildSystem import build_files

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class Pure(unittest.TestCase):
    def test_scope_changes_and_replacement_rejected(self):
        rows = F.changes({'a': 'AND2', 'Tpu/Core/Sram/r': 'DFF'},
                         {'a': 'AND2', 'Tpu/Core/Sram/r': 'DFF', 'b': 'BUFV32RD_12TR40'})
        F.validate_changes(rows)
        with self.assertRaises(ValueError):
            F.validate_changes(F.changes({'a': 'DFF'}, {'a': 'BUFV32RD_12TR40'}))

    def test_new_source_and_old_clock_constraints(self):
        files = build_files()
        text = files['tools/System.tcl'].decode()
        self.assertIn('SOURCE_ID ' + F.REV, text)
        self.assertIn('SYSTEM_STAGE: candidate_saved', text)
        self.assertIn('inspect_core_clk core_csr_clk', text)
        self.assertIn('set_dont_touch $Scope true', text)


@unittest.skipIf(os.name == 'nt', 'POSIX fake EDA integration is run in WSL')
class Flow(unittest.TestCase):
    def case(self, mode='ok', structural_bad=False):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            soc = home / 'soc'
            soc.mkdir()
            original = soc / 'tpusoc_frontend_20261110_707cd7f_ZKpdeM'
            original.mkdir()
            (original / 'source.sv').write_text('TEST_ONLY_SOURCE')
            (original / 'MANIFEST.sha256').write_text(F.sha(original / 'source.sv') + '  source.sv\n')
            std = home / 'std.db'; std.write_text('TEST_STD')
            ram = home / 'RAMSP1024X16_tt_1p10v_1p10v_25c.db'; ram.write_text('TEST_RAM')
            (original / 'library_sha256.txt').write_text(''.join(F.sha(p) + '  ' + str(p) + '\n' for p in (std, ram)))
            acc = soc / F.ACC_NAME
            (acc / 'inputs').mkdir(parents=True)
            (acc / 'mapped').mkdir()
            (acc / 'PACKAGE.sha256').write_text(F.sha(original / 'source.sv') + '  ../bad\n')
            # A tiny valid recovery package manifest, independent of design artifacts.
            (acc / 'tool.py').write_text('TEST_RECOVERY_TOOL')
            (acc / 'PACKAGE.sha256').write_text(F.sha(acc / 'tool.py') + '  tool.py\n')
            for suffix in ('ddc', 'v'):
                (acc / ('inputs/baseline.' + suffix)).write_text('TEST_BASELINE_' + suffix)
                (acc / ('mapped/candidate.' + suffix)).write_text('TEST_CANDIDATE_' + suffix)
            sdc = 'create_clock -name CoreClock -period 6.666667 clk\n'
            (acc / 'inputs/baseline.sdc').write_text(sdc)
            (acc / 'mapped/candidate.sdc').write_text(sdc + 'set_fix_hold CoreClock\n')
            before = {'Tpu/Core/Sram/M' + str(i): 'RAMSP1024X16' for i in range(56)}
            before['Tpu/Core/Matrix/reg'] = 'DFF_TEST'
            after = dict(before)
            after['Tpu/Core/new_buffer'] = 'AND_TEST' if structural_bad else 'BUFV32RD_12TR40'
            for name, data in [('baseline_leaves.tsv', before), ('candidate_leaves.tsv', after),
                               ('outside_before.tsv', {n: r for n, r in before.items() if not n.startswith('Tpu/Core/Sram/')}),
                               ('outside_after.tsv', {n: r for n, r in after.items() if not n.startswith('Tpu/Core/Sram/')})]:
                (acc / 'mapped' / name).write_text(''.join(n + '\t' + r + '\n' for n, r in data.items()))
            (acc / 'mapped/summary.txt').write_text('SOURCE_ID: ' + F.REV + '_with_platform_icb\nSETUP_STATUS: PASS\nHOLD_STATUS: PASS\n')
            original_hashes = {str(p): F.sha(p) for p in (original / 'source.sv', original / 'library_sha256.txt', std, ram)}
            copies = {str(p): F.sha(p) for p in (acc / 'inputs').iterdir()}
            (acc / 'RecoveryInputs.json').write_text(json.dumps({'source_commit': F.REV, 'original_run': str(original),
                'original_sha256': original_hashes, 'new_inputs_sha256': copies}))
            (acc / 'SourceUnchanged.json').write_text(json.dumps({'original_unchanged': True, 'input_copies_unchanged': True, 'native_exit': 0}))
            (acc / 'RecoveryOutputs.json').write_text(json.dumps({p.relative_to(acc).as_posix(): F.sha(p) for p in (acc / 'mapped').iterdir()}))
            out = soc / 'new_system_test'; out.mkdir()
            files = build_files()
            cfg = json.loads(files['Config.json'])
            cfg['original_manifest_sha256'] = F.sha(original / 'MANIFEST.sha256')
            cfg['accelerator_recovery_package_sha256'] = F.sha(acc / 'PACKAGE.sha256')
            files['Config.json'] = json.dumps(cfg).encode()
            for name, b in files.items():
                p = out / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
            (out / 'PACKAGE.sha256').write_text(''.join(hashlib.sha256(b).hexdigest() + '  ' + n + '\n' for n, b in files.items()))
            platform = soc / 'tpusoc_system_base_20261106_GamjxW'
            (platform / 'sram_db').mkdir(parents=True)
            (platform / 'contract').mkdir()
            (platform / 'cpu').mkdir()
            tcm = platform / 'TcmMacro.sv'; tcm.write_bytes(files['tools/TcmMacro.sv'])
            cpu = platform / 'cpu/e203_cpu_top.v'; cpu.write_text('TEST_CPU_SOURCE')
            hdr = platform / 'cpu/config.vh'; hdr.write_text('TEST_INCLUDE')
            shared = platform / 'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db'; shared.write_text('TEST_SHARED_DB')
            source_list = platform / 'Sources.tcl'
            source_list.write_text('set Sources ' + F.tcl_list([platform / 'frozen_accelerator.v', tcm, cpu]) + '\nset Includes ' + F.tcl_list([cpu.parent]) + '\n')
            (platform / 'contract/run.log').write_text('PASS TCM_PORT_CONTRACT: DW=64 DP=32768 banks=8 macros=32 checks=96;\nPASS TCM_PORT_CONTRACT: DW=32 DP=65536 banks=16 macros=32 checks=128;\nPASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros;\n')
            (platform / 'contract/status.txt').write_text('PASS')
            clock = soc / 'tpusoc_clock_port_review_20261106_TiLrj3'; clock.mkdir()
            (clock / 'Inputs.json').write_text(json.dumps({'source': str(platform), 'inputs': {str(p): F.sha(p) for p in (source_list, tcm, cpu, hdr, shared)}}))
            originals = {str(p): F.sha(p) for d in (acc, original, platform, clock) for p in d.rglob('*') if p.is_file()}
            fake = home / 'fake_eda'
            fake.write_text('''#!/usr/bin/env python3
import os,sys,json
from pathlib import Path
mode=os.environ['MODE']
if sys.argv[-1].endswith('Equiv.tcl'):
    for n in 'black_boxes_r black_boxes_i report_unmatched_points report_failing_points report_aborted_points report_unverified_points'.split():Path(n+'.rpt').write_text('TEST_ONLY_NO_POINTS')
    Path('EquivStatus.tsv').write_text('MATCH_RETURN\\t1\\nVERIFY_RETURN\\t'+('0' if mode=='fmfail' else '1')+'\\nRESULT\\tHOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING\\n')
    print('FAKE_FM_ONLY')
else:
    p=Path(os.environ['TPU_SYSTEM_OUT'])
    for n in 'baseline.ddc baseline.v baseline.sdc candidate.ddc candidate.v candidate.sdc system_guidance.svf system_name_map.tcl area_breakdown.tsv area_totals.txt check_design.rpt check_timing.rpt units.rpt setup.rpt hold.rpt'.split():
        if mode=='missing' and n=='candidate.ddc':continue
        (p/n).write_text('TEST_ONLY')
    d={'TOP':'e203_cpu_top','SOURCE_ID':'707cd7f4a0a4d416d11bac71112980079e0a9d34','FROZEN_ACCELERATOR':'UNCHANGED','PRIVATE_SRAM_COUNT':'56','SHARED_SRAM_COUNT':'64','SHARED_CAPACITY_BYTES':'524288','SETUP_WNS_NS':'0.001','HOLD_WNS_NS':'-0.1' if mode=='holdfail' else '0.001','SETUP_STATUS':'PASS','HOLD_STATUS':'FAIL' if mode=='holdfail' else 'PASS','SYSTEM_LIBRARY_AREA_UM2':'3000000'}
    (p/'summary.txt').write_text(''.join(k+': '+v+'\\n' for k,v in d.items()))
    if mode=='error':print('Error: FAKE_NATIVE_ERROR_ZERO_EXIT')
    print('SYSTEM_MAPPING_REPORTS_COMPLETE: TEST_ONLY')
''')
            fake.chmod(0o755)
            env = dict(os.environ, HOME=str(home), FM_BIN=str(fake), DC_BIN=str(fake), MODE=mode)
            result = subprocess.run(['python3', str(out / 'tools/SystemFlow.py'), str(out)], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
            self.assertTrue(all(F.sha(Path(p)) == h for p, h in originals.items()))
            prog = json.loads((out / 'FlowProgress.json').read_text())
            if structural_bad or mode == 'fmfail':
                self.assertFalse((out / 'system/mapped').exists())
            if mode == 'missing':
                self.assertTrue((out / 'system/mapped/baseline.ddc').exists())
            return result.returncode, result.stdout.decode(), prog

    def test_full_collector_and_platform_integrity(self):
        code, log, p = self.case()
        self.assertEqual(code, 0, log)
        self.assertEqual(len(p['successful_stages']), 4)

    def test_non_buffer_structural_change_stops_before_system(self):
        code, log, p = self.case(structural_bad=True)
        self.assertNotEqual(code, 0, log)
        self.assertEqual(p['failed_stage'], 'accelerator_review')

    def test_fm_failure_cannot_start_system(self):
        code, log, p = self.case('fmfail')
        self.assertNotEqual(code, 0, log)
        self.assertEqual(p['failed_stage'], 'hold_equivalence')

    def test_system_native_error_rejected(self):
        code, log, p = self.case('error')
        self.assertNotEqual(code, 0, log)

    def test_missing_candidate_preserves_baseline(self):
        code, log, p = self.case('missing')
        self.assertNotEqual(code, 0, log)

    def test_negative_hold_is_reported_fail(self):
        code, log, p = self.case('holdfail')
        self.assertEqual(code, 0, log)
        self.assertIn('HOLD_STATUS: FAIL', log)


if __name__ == '__main__':
    unittest.main()
