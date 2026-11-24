"""System-refresh parsing and acceptance tests; fake DC tests exercise orchestration only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import System
from Review import sha

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


class SystemTest(unittest.TestCase):
    def summary(self):
        return dict(TOP='e203_cpu_top',FROZEN_ACCELERATOR='UNCHANGED',PRIVATE_SRAM_COUNT='56',
            SHARED_SRAM_COUNT='64',SHARED_CAPACITY_BYTES='524288',SETUP_WNS_NS='0.001',HOLD_WNS_NS='-0.01',
            SETUP_STATUS='PASS',HOLD_STATUS='FAIL',SYSTEM_LIBRARY_AREA_UM2='2600000')

    def test_parse_only_expected_tcl_lists(self):
        result=System.parse_sources('set Sources [list {/x/a.v} {/path with space/b.v}]\nset Includes [list {/x}]\n')
        self.assertEqual(result['Sources'][1],'/path with space/b.v')
        for text in ['set Sources [exec wrong]\nset Includes [list ]\n',
                     'set Sources [list {/a}; unsafe]\nset Includes [list ]\n']:
            with self.assertRaises(ValueError): System.parse_sources(text)

    def test_timing_fail_preserved_and_invalid_boundary_rejected(self):
        data=self.summary()
        System.validate_summary(data)
        data['HOLD_STATUS']='PASS'
        with self.assertRaises(ValueError): System.validate_summary(data)
        data=self.summary(); data['PRIVATE_SRAM_COUNT']='55'
        with self.assertRaises(ValueError): System.validate_summary(data)
        data=self.summary(); data['SETUP_WNS_NS']='nan'
        with self.assertRaises(ValueError): System.validate_summary(data)

    def test_historical_source_modification_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cpu.v'; path.write_text('old source')
            ledger={str(path):sha(path)}
            System.checked(path,ledger)
            path.write_text('changed source')
            with self.assertRaises(ValueError): System.checked(path,ledger)

    @unittest.skipIf(os.name=='nt','POSIX StageWatch required')
    def test_collector_with_fake_dc(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); soc=home/'soc'; soc.mkdir()
            out=home/'out'; (out/'tools').mkdir(parents=True)
            for name,path in [('System.py',HERE/'System.py'),('Review.py',HERE/'Review.py'),
                ('StageWatch.py',ROOT/'Server/SystemBackend/StageWatch.py'),
                ('TcmMacro.sv',ROOT/'Server/SystemBackend/TcmMacro.sv')]:
                shutil.copy2(path,out/'tools'/name)
            run=soc/'tpusoc_refresh_dc_20261109_fixture'; (run/'mapped').mkdir(parents=True)
            (run/'payload.txt').write_text('frozen payload')
            (run/'MANIFEST.sha256').write_text(sha(run/'payload.txt')+'  payload.txt\n')
            manifest_sha=sha(run/'MANIFEST.sha256')
            (run/'mapped/candidate.v').write_text('current candidate fixture')
            libs=[home/'std.db',home/'private.db']
            for path in libs: path.write_text('fixture library')
            (run/'library_sha256.txt').write_text(''.join(sha(p)+'  '+str(p)+'\n' for p in libs))
            review=soc/'review'; (review/'candidate').mkdir(parents=True)
            (review/'candidate/leaves.tsv').write_text('name\tref\tregion\ncell\tBUF\toutside\n')
            equiv=soc/'tpusoc_hold_equiv_20261109_fixture'; equiv.mkdir()
            (equiv/'EquivSummary.json').write_text(json.dumps(dict(original_run=str(run),review=str(review),
                input_unchanged=True,native_exit=0,result='HOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING',
                status=dict(MATCH_RETURN=['1'],VERIFY_RETURN=['1']))))
            (equiv/'EquivInputs.json').write_text(json.dumps({'sha256':{str(run/'mapped/candidate.v'):sha(run/'mapped/candidate.v')}}))
            (equiv/'SourceUnchanged.json').write_text('{"unchanged":true}')
            for name in ['EquivStatus.tsv','fm.log','black_boxes_r.rpt','black_boxes_i.rpt']:
                (equiv/name).write_text('fixture evidence')
            old=soc/'tpusoc_system_base_20261106_GamjxW'
            for name in ['tools','sram_db','contract','platform']: (old/name).mkdir(parents=True,exist_ok=True)
            shutil.copy2(out/'tools/TcmMacro.sv',old/'tools/TcmMacro.sv')
            for name in ['e203_cpu_top.v','sirv_sim_ram.v']: (old/'platform'/name).write_text('fixture cpu')
            (old/'frozen_accelerator.v').write_text('old candidate unused')
            (old/'Sources.tcl').write_text('set Sources '+System.tcl_list([old/'frozen_accelerator.v',old/'tools/TcmMacro.sv',old/'platform/e203_cpu_top.v',old/'platform/sirv_sim_ram.v'])+'\nset Includes '+System.tcl_list([old/'platform'])+'\n')
            (old/'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db').write_text('shared fixture library')
            (old/'contract/status.txt').write_text('PASS')
            (old/'contract/run.log').write_text('PASS TCM_PORT_CONTRACT: DW=64 DP=32768 banks=8 macros=32 checks=96;\nPASS TCM_PORT_CONTRACT: DW=32 DP=65536 banks=16 macros=32 checks=128;\nPASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros;\n')
            clock=soc/'tpusoc_clock_port_review_20261106_TiLrj3'; clock.mkdir()
            (clock/'Inputs.json').write_text(json.dumps({'source':str(old),'inputs':{str(p):sha(p) for p in old.rglob('*') if p.is_file()}}))
            fake=home/'fake_dc'
            summary=''.join(k+': '+v+'\n' for k,v in self.summary().items())
            fake.write_text('''#!/usr/bin/env python3
import os,pathlib
out=pathlib.Path(os.environ['TPU_SYSTEM_OUT'])
for name in ['candidate.ddc','candidate.v','candidate.sdc','area_breakdown.tsv','system_guidance.svf']:
    (out/name).write_text('fixture output')
(out/'summary.txt').write_text('''+repr(summary)+''')
(out/'area_totals.txt').write_text('fixture area totals')
print('SYSTEM_MAPPING_REPORTS_COMPLETE: fixture')
''')
            fake.chmod(0o755)
            result=subprocess.run(['python3',str(out/'tools/System.py'),'--out',str(out),'--manifest-sha',manifest_sha],
                env=dict(os.environ,HOME=str(home),DC_BIN=str(fake)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=25)
            self.assertEqual(result.returncode,0,result.stdout.decode())
            summary=json.loads((out/'SystemSummary.json').read_text())
            self.assertEqual(summary['summary']['HOLD_STATUS'],'FAIL')
            self.assertEqual(summary['result'],'NEW_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING')
            self.assertTrue(summary['original_inputs_unchanged'])
            self.assertTrue((out/'SystemDcReports.tar.gz').is_file())


if __name__=='__main__': unittest.main()
