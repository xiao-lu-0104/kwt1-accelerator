"""New PR source isolation and initial-placement collector tests; fake ICC2 only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from BuildPr import build_files
from SystemFlow import REV, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


@unittest.skipIf(os.name == 'nt', 'POSIX/native-process fixtures run in WSL')
class Pr(unittest.TestCase):
    def case(self, mode='ok'):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); soc = home / 'soc'; soc.mkdir()
            out = soc / 'new_pr_fixture'; out.mkdir()
            for name, b in build_files().items():
                p = out / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
            flow = soc / 'tpusoc_system_dc_20261110_707cd7f_current'; flow.mkdir()
            (flow / 'tool.txt').write_text('TEST_SYSTEM_TOOL')
            (flow / 'PACKAGE.sha256').write_text(sha(flow / 'tool.txt') + '  tool.txt\n')
            (flow / 'Config.json').write_text('TEST_CONFIG')
            (flow / 'FlowProgress.json').write_text(json.dumps({'source_commit': REV, 'result': 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING',
                'inputs_unchanged': True, 'successful_stages': ['hold_structure_review', 'hold_native_incremental_equivalence', 'system_inputs_frozen', 'e203_system_dc_reports']}))
            (flow / 'SourceUnchanged.json').write_text('{"unchanged":true}')
            system = flow / 'system'; mapped = system / 'mapped'; mapped.mkdir(parents=True)
            (mapped / 'candidate.v').write_text('module e203_cpu_top;\nBUF U0 ();\nRAMSP1024X16 P0 ();\nRAMSP4096X16 S0 ();\nendmodule\n')
            (mapped / 'candidate.sdc').write_text('set_units -time ns\ncreate_clock [get_ports clk] -name CoreClock -period 6.66667\n')
            (mapped / 'area_breakdown.tsv').write_text('TEST_CURRENT_SYSTEM_AREA')
            outputs = {p.name: sha(p) for p in mapped.iterdir()}
            (system / 'SystemOutputs.json').write_text(json.dumps(outputs))
            summary = {'TOP': 'e203_cpu_top', 'SOURCE_ID': REV, 'FROZEN_ACCELERATOR': 'UNCHANGED', 'PRIVATE_SRAM_COUNT': '56', 'SHARED_SRAM_COUNT': '64',
                'SHARED_CAPACITY_BYTES': '524288', 'SETUP_WNS_NS': '0.001', 'HOLD_WNS_NS': '0.001', 'SETUP_STATUS': 'PASS', 'HOLD_STATUS': 'PASS', 'SYSTEM_LIBRARY_AREA_UM2': '3000000'}
            (system / 'SystemSummary.json').write_text(json.dumps({'result': 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING', 'original_inputs_unchanged': True, 'summary': summary}))
            (system / 'SystemInputs.json').write_text(json.dumps({'source_commit': REV, 'accelerator_run': str(soc / 'tpusoc_hold_recovery_20261110_707cd7f_Bwf2gR'),
                'sha256': {str(mapped / 'candidate.v'): sha(mapped / 'candidate.v')}}))
            power = soc / 'tpusoc_task_power_20261110_707cd7f_current'; power.mkdir()
            (power / 'tool.txt').write_text('TEST_POWER_TOOL')
            (power / 'PACKAGE.sha256').write_text(sha(power / 'tool.txt') + '  tool.txt\n')
            (power / 'Inputs.json').write_text(json.dumps({'source_commit': REV, 'system': str(system), 'inputs': {str(mapped / 'candidate.v'): sha(mapped / 'candidate.v')}}))
            tasks = {}
            for name in ('ff1', 'encoder'):
                (power / name).mkdir(); saif = power / name / 'task.saif'; saif.write_text('NEW_TASK_ACTIVITY_' + name)
                tasks[name] = {'task': {'status': 'CURRENT_TASK_GOLDEN_AND_ACTIVITY_PASS', 'saif_sha256': sha(saif), 'cycles': 1000, 'duration_seconds': 0.001},
                    'system_power': {'total_w': 0.075, 'dynamic_w': 0.07, 'leakage_w': 0.005}, 'accelerator_power': {'total_w': 0.062}}
            (power / 'CurrentPowerSummary.json').write_text(json.dumps({'result': 'CURRENT_SYSTEM_TASK_POWER_REPORTS_COMPLETE_REVIEW_PENDING', 'tasks': tasks}))
            reference = soc / 'tpusoc_system_pr_resume_20261109_good'; reference.mkdir()
            (reference / 'NewPrSummary.json').write_text(json.dumps({'result': 'NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING', 'original_inputs_unchanged': True}))
            snapshots = {}
            for label in ('rvt', 'private', 'shared'):
                p = reference / ('library_' + label) / (label + '.ndm'); p.mkdir(parents=True)
                (p / 'ref.dat').write_text('TEST_REFERENCE_' + label)
                snapshots[str(home / 'original' / (label + '.ndm'))] = {'ref.dat': sha(p / 'ref.dat')}
            assets = home / 'assets'; assets.mkdir()
            tf = assets / 'current.tf'; tf.write_text('TEST_TF')
            tech = assets / 'tech.lef'; tech.write_text('TEST_TECH_LEF')
            def lef(ref, w, h):
                return 'MACRO '+ref+'\n SIZE %s BY %s ;\n PIN VDD\n USE POWER ;\n END VDD\n PIN VSS\n USE GROUND ;\n END VSS\nEND '%(w,h)+ref+'\n'
            std = assets / 'std.lef'; std.write_text(lef('BUF', 1, 2))
            private = assets / 'RAMSP1024X16.lef'; private.write_text(lef('RAMSP1024X16', 80, 110))
            shared = assets / 'RAMSP4096X16.lef'; shared.write_text(lef('RAMSP4096X16', 80, 110))
            (reference / 'PrRecoveryInputs.json').write_text(json.dumps({'reference_snapshots': snapshots, 'inputs': {str(shared): sha(shared)}}))
            fake = home / 'fake_icc'
            fake.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
p=Path.cwd();(p/'system_707cd7f.nlib').mkdir();(p/'system_707cd7f.nlib/design.dat').write_text('TEST_NEW_LIBRARY')
for n in ('initial_floorplan.def','placed_707cd7f.def'):(p/n).write_text('TEST_NEW_707CD7F_DEF')
(p/'report_units.rpt').write_text('length : 1.00um\\n')
(p/'report_placement.rpt').write_text('Total hard macro to hard macro overlaps: 0\\n')
(p/'core_bbox.txt').write_text('{0 0} {2000 2000}')
rows=['instance\\tref\\tx1\\ty1\\tx2\\ty2']
for i in range(120):
    x=(i%12)*150;y=(i//12)*150
    if os.environ['MODE']=='overlap' and i==1:x=y=0
    rows.append('M%d\\t%s\\t%s\\t%s\\t%s\\t%s'%(i,'RAMSP1024X16' if i<56 else 'RAMSP4096X16',x,y,x+82.46,y+111.1314))
(p/'macros.tsv').write_text('\\n'.join(rows)+'\\n')
if os.environ['MODE']=='error':print('Error: TEST_NATIVE_ZERO_EXIT_ERROR')
print('NEW_SYSTEM_INITIAL_PLACEMENT_NATIVE_COMPLETE')
'''); fake.chmod(0o755)
            physical = soc / 'tpusoc_icc2_start_20261108_mTq1LE'; physical.mkdir()
            (physical / 'PrInputs.json').write_text(json.dumps({'selection': {'technology': str(tf), 'tech_lef': str(tech), 'std_lef': str(std), 'macro_lef': str(private)},
                'inputs': {str(p): sha(p) for p in (tf, tech, std, private)}, 'icc2': str(fake), 'icc2_flag': '-file'}))
            cfg = json.loads((out / 'Config.json').read_text()); cfg.update(system_package_sha256=sha(flow / 'PACKAGE.sha256'), power_package_sha256=sha(power / 'PACKAGE.sha256'))
            (out / 'Config.json').write_text(json.dumps(cfg))
            (out / 'PACKAGE.sha256').write_text('TEST_PACKAGE_ALREADY_CHECKED_BY_LAUNCHER')
            if mode == 'ndmmutated':
                (reference / 'library_rvt/rvt.ndm/ref.dat').write_text('CHANGED_REFERENCE')
            if mode == 'systemmutated': (mapped / 'candidate.v').write_text('CHANGED_NETLIST')
            originals = {str(p): sha(p) for d in (flow, power, reference, physical, assets) for p in d.rglob('*') if p.is_file()}
            result = subprocess.run(['python3', str(out / 'tools/PrFlow.py'), str(out)], env=dict(os.environ, HOME=str(home), MODE=mode),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
            self.assertTrue(all(sha(Path(p)) == h for p, h in originals.items()))
            if mode in ('ndmmutated', 'systemmutated'): self.assertFalse((out / 'design/system_707cd7f.nlib').exists())
            if mode == 'overlap':
                self.assertTrue((out / 'design/system_707cd7f.nlib').exists())
                self.assertFalse((out / 'NewPrSummary.json').exists())
            if result.returncode == 0:
                summary = json.loads((out / 'NewPrSummary.json').read_text())
                self.assertEqual(summary['source_commit'], REV)
                self.assertEqual(summary['macro_count'], 120)
                self.assertIn('system_707cd7f.nlib', (out / 'OpenLayout.tcl').read_text())
            return result.returncode, result.stdout.decode()

    def test_full_current_system_and_ref_only_placement_collector(self):
        code, log = self.case(); self.assertEqual(code, 0, log)

    def test_changed_ndm_rejected_before_native(self):
        code, log = self.case('ndmmutated'); self.assertNotEqual(code, 0, log)

    def test_changed_system_netlist_rejected_before_native(self):
        code, log = self.case('systemmutated'); self.assertNotEqual(code, 0, log)

    def test_native_error_with_zero_exit_rejected(self):
        code, log = self.case('error'); self.assertNotEqual(code, 0, log)

    def test_overlap_keeps_checkpoint_but_does_not_accept(self):
        code, log = self.case('overlap'); self.assertNotEqual(code, 0, log)


if __name__ == '__main__':
    unittest.main()
