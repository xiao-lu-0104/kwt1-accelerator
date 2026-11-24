"""Current driver/guard/report parsing tests, not actual gate simulation or power evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
for path in (ROOT/'Server/SharedAsic',ROOT/'Server/SystemBackend',ROOT/'Server/RefreshDc'):
    sys.path.append(str(path))
import Power
import Tasks
import Guards
from BuildFirmware import adapt_main


def fixture():
    def module(name,body):return 'module '+name+';\n'+body+'\nendmodule\n'
    text=module('e203_subsys_nice_core','wire nice_rst_n;\nTpuNice Tpu();')
    text+=module('TpuNice','TpuCore Core();')
    text+=module('TpuCore','TpuMatmul Matrix();\nTpuDma Dma();\nTpuSram Sram();')
    text+=module('TpuMatmul','BiasBuffer BiasBuffer();\n'+'\n'.join('TpuDot \\RowPipelines[%d].Dot  ();'%i for i in range(4)))
    text+=module('TpuDot','wire InputValid; wire [127:0] InputOperandA,InputOperandB;')
    text+=module('BiasBuffer','wire WriteValid; wire [127:0] WriteData;')
    text+=module('TpuDma','wire WriteDataValid,ReadDataValid,ReadDataReady,ReadDataLast,ReadDataError,SramReadValid,SramReadReady;\nwire [127:0] WriteData,ReadData,SramReadData;')
    text+=module('TpuSram','\n'.join('RAMSP1024X16 Macro%d ();'%i for i in range(56)))
    return text


class CurrentPowerTests(unittest.TestCase):
    def validate_fixture(self,mutate=None):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'ff1').mkdir();(out/'Inputs.json').write_text('{"inputs":{}}')
            log='''PASS SHARED: kind=1 layers=1 values=25344 cycles=1000 DMA_read_bytes=45952 DMA_write_bytes=50688 loaded_bytes=45960
PASS PHYSICAL_TCM_INIT: ITCM_writes=32768 DTCM_writes=65536 ITCM_readback=32768 DTCM_readback=65536;
PHYSICAL_TCM_INIT_FINAL: done=1 released=1
INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0
ICB_MIRROR_FINAL: divergence_observed=0
TASK_ACTIVITY_FINAL: started=1 stopped=1
EFFECTIVE_GUARD_FINAL: complete=1
SHARED_TCM_GUARD_FINAL: complete=1
TASK_ACTIVITY_END: cycles=1000 duration_ns=6667.000
'''
            if mutate=='guard':log=log.replace('EFFECTIVE_GUARD_FINAL: complete=1','EFFECTIVE_GUARD_FINAL: complete=0')
            (out/'ff1/run.log').write_text(log)
            saif='(SAIFILE (TIMESCALE 1 ps) (DURATION 6667000) (INSTANCE Cpu (INSTANCE u_e203_cpu (NET (idle (TX 6667000) (TC 1)))) (INSTANCE u_e203_srams)))'
            if mutate=='scope':saif=saif.replace('u_e203_srams','unrelated_scope')
            (out/'ff1/task.saif').write_text(saif)
            Tasks.validate(out,'ff1')
            result=json.loads((out/'ff1/Activity.json').read_text())
            self.assertEqual(result['TX_nonzero_entries'],1)
            self.assertFalse(result['unknown_waiver'])

    def test_current_task_validation_retains_unknown_statistics(self):
        self.validate_fixture()

    def test_failed_guard_or_missing_system_scope_rejected(self):
        for mode in ('guard','scope'):
            with self.assertRaises(ValueError):self.validate_fixture(mode)

    def test_new_ff1_argument_order_only(self):
        old='TpuRunFf1(TPU_INPUT, TPU_PARAMETERS, TPU_OUTPUT, Mail[6])'
        self.assertEqual(adapt_main(old),'TpuRunFf1(TPU_INPUT, TPU_PARAMETERS, Mail[6], TPU_OUTPUT)')
        with self.assertRaises(ValueError):adapt_main('unknown firmware interface')

    def test_block_counts_keep_strict_bench(self):
        required=['UNKNOWN_LOADER_COMMAND_READY','UNKNOWN_LOADER_RESPONSE_VALID','UNKNOWN_LOADER_READ_DATA',
            'Result !== ExpectedHost[WordIndex]','TaskActivity.StartWindow();','TaskActivity.EndRequested = 1;',
            'TcmInitializer.Done && TcmInitializer.Released']
        bench='\n'.join(required+['Executes != (Kind == 1 ? 99 : 10)','Stores != (Kind == 1 ? 99 : 1)'])
        updated=Tasks.current_bench(bench)
        self.assertEqual(updated.count('Kind == 1 ? 4'),2)
        self.assertIn('Result !== ExpectedHost[WordIndex]',updated)
        with self.assertRaises(ValueError):Tasks.current_bench(bench+'\n`DTCM[Index]=0;')

    def test_guard_covers_four_dot_pipelines_and_56_macros(self):
        source=Guards.effective_guard(fixture())
        for i in range(4):self.assertIn('EFFECTIVE_DATA_X DOT_'+str(i),source)
        self.assertEqual(source.count('MACRO_ENABLE_X '),56)
        self.assertNotIn('force ',source)
        with self.assertRaises(ValueError):Guards.effective_guard(fixture().replace('TpuDot \\RowPipelines[3].Dot  ();',''))

    def test_explicit_units_and_component_sum(self):
        text='Cell Internal Power = 20 mW\nNet Switching Power = 1000 uW\nTotal Dynamic Power = 21 mW\nCell Leakage Power = 100 uW\n'
        self.assertAlmostEqual(Power.power_values(text)['total_w'],.0211)
        with self.assertRaises(ValueError):Power.power_values(text.replace('21 mW','21 N/A'))
        with self.assertRaises(ValueError):Power.power_values(text.replace('21 mW','22 mW'))

    def test_zero_activity_groups_allowed_but_macro_count_required(self):
        text='Totals ( 6 cells ) 0 W 0 W 0 W 1 uW\n'
        self.assertEqual(Power.group_values(text,6)['dynamic_w'],0)
        with self.assertRaises(ValueError):Power.group_values(text,7)

    def test_mutated_current_activity_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp); (out/'ff1').mkdir()
            saif=out/'ff1/task.saif';saif.write_text('new activity')
            (out/'Inputs.json').write_text('{"inputs":{}}')
            (out/'ff1/Activity.json').write_text(json.dumps({'status':'CURRENT_TASK_GOLDEN_AND_ACTIVITY_PASS','saif_sha256':'wrong'}))
            with self.assertRaises(ValueError):Power.estimate(out,'ff1')

    @unittest.skipIf(os.name=='nt','POSIX StageWatch required')
    def test_current_power_collector_fake_eda(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'tools').mkdir();(out/'ff1').mkdir();(out/'system/mapped').mkdir(parents=True)
            shutil.copy2(ROOT/'Server/SystemBackend/StageWatch.py',out/'tools/StageWatch.py')
            saif=out/'ff1/task.saif';saif.write_text('fresh fixture activity')
            (out/'Inputs.json').write_text(json.dumps({'inputs':{},'system':str(out/'system'),'libraries':['std','private','shared']}))
            (out/'ff1/Activity.json').write_text(json.dumps({'status':'CURRENT_TASK_GOLDEN_AND_ACTIVITY_PASS',
                'saif_sha256':Power.sha(saif),'duration_seconds':.001,'TX_nonzero_entries':1}))
            fake=out/'fake_dc'
            fake.write_text('''#!/usr/bin/env python3
import os,pathlib
p=pathlib.Path(os.environ['NEW_POWER_CASE'])
(p/'ToolStatus.txt').write_text('NETLIST: UNCHANGED\\nTIMING_BUDGETS: UNCHANGED\\n')
(p/'power.rpt').write_text('Cell Internal Power = 20 mW\\nNet Switching Power = 1 mW\\nTotal Dynamic Power = 21 mW\\nCell Leakage Power = 100 uW\\n')
cov='Nets 8(80.00%) 1(10.00%) 1(10.00%) 10\\nPorts 1(100.00%) 0(0.00%) 0(0.00%) 1\\nPins 8(80.00%) 1(10.00%) 1(10.00%) 10\\n'
for n in ('saif_global','saif_hierarchy','cpu_core_coverage','accelerator_coverage','shared_tcm_coverage'):(p/(n+'.rpt')).write_text(cov)
groups={'ACCELERATOR_LOGIC_AND_INTERFACES':100,'ACCELERATOR_PRIVATE_SRAM':56,'REUSED_CPU_AND_INTERNAL_ICB_LOGIC':20,'SHARED_ITCM_MACROS':32,'SHARED_DTCM_MACROS':32,'SHARED_TCM_BINDING_LOGIC':3,'OTHER_SYSTEM_LOGIC':6}
(p/'groups.tsv').write_text(''.join(k+'\\t'+str(v)+'\\n' for k,v in groups.items()))
for k,n in groups.items():(p/(k+'_power.rpt')).write_text('Totals ( %d cells ) 1 mW 0 W 1 mW 1 uW\\n'%n)
print('CURRENT_TASK_POWER_REPORT_COMPLETE')
''');fake.chmod(0o755)
            previous=os.environ.get('DC_BIN');os.environ['DC_BIN']=str(fake)
            try:Power.estimate(out,'ff1')
            finally:
                if previous is None:os.environ.pop('DC_BIN',None)
                else:os.environ['DC_BIN']=previous
            data=json.loads((out/'ff1/PowerSummary.json').read_text())
            self.assertAlmostEqual(data['system_power']['total_w'],.0211)
            self.assertAlmostEqual(data['system_task_energy_j'],.0000211)
            self.assertEqual(data['global_coverage_tables'][0]['objects']['nets']['default']['count'],1)
            self.assertEqual(data['task']['TX_nonzero_entries'],1)
            before={str(p.relative_to(out)):Power.sha(p) for p in out.rglob('*') if p.is_file()}
            recovered=out/'recovered'
            previous=os.environ.get('DC_BIN');os.environ['DC_BIN']=str(fake)
            try:Power.estimate(out,'ff1',report_root=recovered,tool_root=out/'tools',limit=3600)
            finally:
                if previous is None:os.environ.pop('DC_BIN',None)
                else:os.environ['DC_BIN']=previous
            self.assertEqual(json.loads((recovered/'ff1/PowerSummary.json').read_text()),data)
            for path,digest in before.items():self.assertEqual(Power.sha(out/path),digest)


if __name__=='__main__':unittest.main()
