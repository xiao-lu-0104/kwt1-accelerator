"""Isolated fake-VCS/DC end-to-end tests of the new real power runner."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from BuildPower import build_files
from SystemFlow import REV, sha, tcl_list
from TestPowerPrep import fixture

HERE = Path(__file__).resolve().parent


@unittest.skipIf(os.name == 'nt', 'POSIX process-group and executable fixtures run in WSL')
class PowerFlow(unittest.TestCase):
    def case(self, mode='ok'):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); soc = home / 'soc'; soc.mkdir()
            out = soc / 'new_power_fixture'; out.mkdir()
            files = build_files()
            for name, b in files.items():
                p = out / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
            flow = soc / 'tpusoc_system_dc_20261110_707cd7f_fixture'; flow.mkdir()
            (flow / 'one.txt').write_text('TEST_SYSTEM_TOOL')
            (flow / 'PACKAGE.sha256').write_text(sha(flow / 'one.txt') + '  one.txt\n')
            cfg = json.loads((out / 'PowerConfig.json').read_text()); cfg['system_package_sha256'] = sha(flow / 'PACKAGE.sha256')
            (out / 'PowerConfig.json').write_text(json.dumps(cfg))
            (out / 'PACKAGE.sha256').write_text(''.join(sha(p) + '  ' + p.relative_to(out).as_posix() + '\n' for p in out.rglob('*') if p.is_file()))
            (flow / 'Config.json').write_text('TEST_CONFIG')
            (flow / 'SourceUnchanged.json').write_text('{"unchanged":true}')
            (flow / 'EquivSummary.json').write_text('{"native_verify":true}')
            (flow / 'FlowProgress.json').write_text(json.dumps({'source_commit': REV, 'result': 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING',
                'inputs_unchanged': True, 'successful_stages': ['hold_structure_review', 'hold_native_incremental_equivalence', 'system_inputs_frozen', 'e203_system_dc_reports']}))
            system = flow / 'system'; (system / 'mapped').mkdir(parents=True)
            src = home / 'platform'; src.mkdir()
            cpu = src / 'e203_cpu_top.v'; cpu.write_text('TEST_CPU_SOURCE')
            header = src / 'config.vh'; header.write_text('TEST_CPU_INCLUDE')
            tcm = src / 'TcmMacro.sv'; tcm.write_text('TEST_TCM_SOURCE')
            (src / 'sram_db').mkdir()
            std = src / 'std.db'; std.write_text('TEST_STD')
            private = src / 'RAMSP1024X16_tt_1p10v_1p10v_25c.db'; private.write_text('TEST_PRIVATE')
            shared = src / 'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db'; shared.write_text('TEST_SHARED')
            original = soc / 'tpusoc_frontend_20261110_707cd7f_ZKpdeM'; original.mkdir()
            (original / 'library_sha256.txt').write_text(''.join(sha(p) + '  ' + str(p) + '\n' for p in (std, private)))
            acc = soc / 'tpusoc_hold_recovery_20261110_707cd7f_Bwf2gR'; (acc / 'mapped').mkdir(parents=True)
            candidate = fixture().replace('TpuNice Tpu();', 'TpuNice Tpu();\nTpuBus Bus();')
            candidate += 'module TpuBus;\nwire Clock,D,Q; wire [1:0] Word; wire [2:0] State;\nDFF_TEST \\Word_reg[0]  (.CK(Clock),.D(D),.Q(Q));\nendmodule\n'
            (acc / 'mapped/candidate.v').write_text(candidate)
            (acc / 'RecoveryInputs.json').write_text(json.dumps({'original_run': str(original), 'original_sha256': {str(std): sha(std), str(private): sha(private)}}))
            (system / 'frozen_accelerator.v').write_text(candidate)
            (system / 'Sources.tcl').write_text('set Sources ' + tcl_list([system / 'frozen_accelerator.v', tcm, cpu]) + '\nset Includes ' + tcl_list([src]) + '\n')
            for n in ('candidate.ddc', 'candidate.sdc', 'system_name_map.tcl', 'area_breakdown.tsv'):
                (system / 'mapped' / n).write_text('TEST_SYSTEM_OUTPUT')
            summary = {'TOP': 'e203_cpu_top', 'SOURCE_ID': REV, 'FROZEN_ACCELERATOR': 'UNCHANGED', 'PRIVATE_SRAM_COUNT': '56',
                'SHARED_SRAM_COUNT': '64', 'SHARED_CAPACITY_BYTES': '524288', 'SETUP_WNS_NS': '0.001', 'HOLD_WNS_NS': '0.001',
                'SETUP_STATUS': 'PASS', 'HOLD_STATUS': 'PASS', 'SYSTEM_LIBRARY_AREA_UM2': '3000000'}
            if mode == 'systemfail': summary.update(HOLD_WNS_NS='-0.1', HOLD_STATUS='FAIL')
            (system / 'SystemSummary.json').write_text(json.dumps({'result': 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING', 'original_inputs_unchanged': True, 'summary': summary}))
            (system / 'SystemOutputs.json').write_text(json.dumps({p.name: sha(p) for p in (system / 'mapped').iterdir()}))
            (system / 'SystemInputs.json').write_text(json.dumps({'source_commit': REV, 'accelerator_run': str(acc), 'old_system': str(src),
                'sha256': {str(p): sha(p) for p in (std, private, shared, cpu, header, tcm, system / 'frozen_accelerator.v')}}))
            old = soc / 'tpusoc_system_tasks_20261106_ZBysEH'; old.mkdir()
            required = ['UNKNOWN_LOADER_COMMAND_READY', 'UNKNOWN_LOADER_RESPONSE_VALID', 'UNKNOWN_LOADER_READ_DATA',
                'Result !== ExpectedHost[WordIndex]', 'TaskActivity.StartWindow();', 'TaskActivity.EndRequested = 1;',
                'TcmInitializer.Done && TcmInitializer.Released', 'Kind == 1 ? 99', 'Kind == 1 ? 99']
            bench = old / 'PhysicalSharedTest.sv'; bench.write_text('\n'.join(required))
            (old / 'candidate.v').write_text('OLD_CANDIDATE_MUST_NOT_BE_USED')
            (old / 'IcbMirror.sv').write_text('TEST_ICB_MIRROR')
            model = src / 'model.v'; model.write_text('module DFF_TEST(CK,D,Q);\ninput CK,D;\noutput Q;\nudp_dff_test U(Q,D,CK);\nendmodule\n')
            (old / 'Task.f').write_text('+incdir+' + str(src) + '\n' + '\n'.join(str(p) for p in (old / 'candidate.v', bench, tcm, cpu)) + '\n-v ' + str(model) + '\n')
            bundle = home / 'bundle'; bundle.mkdir()
            for d in (bundle / 'Vectors', bundle / 'Vectors/Ff1_normal'):
                d.mkdir(parents=True, exist_ok=True)
                for n in ('Input.hex', 'Fractions.hex', 'Layer0.hex', 'Expected0.hex'): (d / n).write_text('0000\n')
            (old / 'Bundle.txt').write_text(str(bundle))
            (old / 'Inputs.json').write_text(json.dumps({'inputs': {str(p): sha(p) for p in old.iterdir() if p.is_file()}}))
            if mode == 'cpumismatch': cpu.write_text('CHANGED_CPU')
            snapshots = {str(p): sha(p) for d in (flow, acc, original, old, src) for p in d.rglob('*') if p.is_file()}
            sim = home / 'fake_sim.py'
            sim.write_text('''#!/usr/bin/env python3
import sys,os
from pathlib import Path
a=dict(x[1:].split('=',1) for x in sys.argv[1:] if x.startswith('+') and '=' in x)
k=int(a['KIND']);cycles=1000 if k else 2000
print('PASS SHARED: kind=%d layers=1 values=%d cycles=%d DMA_read_bytes=%d DMA_write_bytes=%d loaded_bytes=%d'%(k,25344 if k else 6336,cycles,45952 if k else 112256,50688 if k else 12672,45960 if k else 112264))
for s in ['PASS PHYSICAL_TCM_INIT: ITCM_writes=32768 DTCM_writes=65536 ITCM_readback=32768 DTCM_readback=65536;','PHYSICAL_TCM_INIT_FINAL: done=1 released=1','INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0','ICB_MIRROR_FINAL: divergence_observed=0','TASK_ACTIVITY_FINAL: started=1 stopped=1','EFFECTIVE_GUARD_FINAL: complete=1','SHARED_TCM_GUARD_FINAL: complete=1']:print(s)
if os.environ['MODE']=='guardfail':print('Fatal: TEST_INVALID_GUARD')
print('TASK_ACTIVITY_END: cycles=%d duration_ns=%.3f'%(cycles,cycles*6.667))
Path(a['TASK_SAIF']).write_text('(SAIFILE (TIMESCALE 1 ps) (DURATION %d) (INSTANCE Cpu (INSTANCE u_e203_cpu (NET (idle (TX 1) (TC 2)))) (INSTANCE u_e203_srams)))'%(cycles*6667))
'''); sim.chmod(0o755)
            vcs = home / 'fake_vcs'; vcs.write_text('''#!/usr/bin/env python3
import sys,os,shutil
from pathlib import Path
p=Path(sys.argv[sys.argv.index('-o')+1]);shutil.copy2(os.environ['FAKE_SIM'],p);p.chmod(0o755)
print('TEST_VCS_COMPILE_ONLY')
'''); vcs.chmod(0o755)
            dc = home / 'fake_dc'; dc.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
p=Path(os.environ['NEW_POWER_CASE'])
(p/'ToolStatus.txt').write_text('NETLIST: UNCHANGED\\nTIMING_BUDGETS: UNCHANGED\\n')
(p/'power.rpt').write_text('Cell Internal Power = 7 mW\\nNet Switching Power = 7 mW\\nTotal Dynamic Power = 14 mW\\nCell Leakage Power = 7 mW\\n')
cov='Nets 8(80.00%) 1(10.00%) 1(10.00%) 10\\nPorts 1(100.00%) 0(0.00%) 0(0.00%) 1\\nPins 8(80.00%) 1(10.00%) 1(10.00%) 10\\n'
for n in ('saif_global','saif_hierarchy','cpu_core_coverage','accelerator_coverage','shared_tcm_coverage'):(p/(n+'.rpt')).write_text(cov)
groups={'ACCELERATOR_LOGIC_AND_INTERFACES':1,'ACCELERATOR_PRIVATE_SRAM':56,'REUSED_CPU_AND_INTERNAL_ICB_LOGIC':1,'SHARED_ITCM_MACROS':32,'SHARED_DTCM_MACROS':32,'SHARED_TCM_BINDING_LOGIC':1,'OTHER_SYSTEM_LOGIC':1}
(p/'groups.tsv').write_text(''.join(k+'\\t'+str(v)+'\\n' for k,v in groups.items()))
for k,n in groups.items():(p/(k+'_power.rpt')).write_text('Totals ( %d cells ) 1 mW 1 mW 2 mW 1 mW\\n'%n)
if os.environ['MODE']=='powererror':print('Error: TEST_ZERO_EXIT_NATIVE_ERROR')
print('CURRENT_TASK_POWER_REPORT_COMPLETE')
'''); dc.chmod(0o755)
            env = dict(os.environ, HOME=str(home), VCS_BIN=str(vcs), DC_BIN=str(dc), FAKE_SIM=str(sim), MODE=mode, PYTHONDONTWRITEBYTECODE='1')
            run = subprocess.run(['python3', str(out / 'tools/Run.py'), str(out)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=35)
            self.assertTrue(all(sha(Path(p)) == h for p, h in snapshots.items()))
            if mode in ('systemfail', 'cpumismatch'):
                self.assertFalse((out / 'simv').exists())
            if mode == 'guardfail':
                self.assertFalse((out / 'ff1/power').exists())
            if run.returncode == 0:
                data = json.loads((out / 'CurrentPowerSummary.json').read_text())
                self.assertEqual(data['tasks']['ff1']['task']['TX_nonzero_entries'], 1)
                self.assertEqual(data['tasks']['encoder']['task']['cycles'], 2000)
            return run.returncode, run.stdout.decode()

    def test_full_new_prepare_sim_validate_power_pipeline(self):
        code, log = self.case()
        self.assertEqual(code, 0, log)

    def test_native_power_error_rejected(self):
        code, log = self.case('powererror')
        self.assertNotEqual(code, 0, log)
        self.assertIn('Native current power report failed', log)

    def test_invalid_task_guard_stops_before_power(self):
        code, log = self.case('guardfail')
        self.assertNotEqual(code, 0, log)
        self.assertIn('Task guard failed', log)

    def test_failed_system_timing_stops_before_simulation(self):
        code, log = self.case('systemfail')
        self.assertNotEqual(code, 0, log)
        self.assertIn('Current system timing is not PASS', log)

    def test_changed_system_cpu_source_stops_before_simulation(self):
        code, log = self.case('cpumismatch')
        self.assertNotEqual(code, 0, log)
        self.assertIn('Input changed', log)


if __name__ == '__main__':
    unittest.main()
