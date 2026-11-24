"""Validate native-map provenance, global coverage comparison and raw evidence retention."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'SharedAsic'))
from NativeMappedPower import prepare,finish
from Prepare import sha

BEFORE='Nets 80(80.00%) 20(20.00%) 0(0.00%) 100\nPorts 10(100.00%) 0(0.00%) 0(0.00%) 10\nPins 800(80.00%) 200(20.00%) 0(0.00%) 1000\n'
AFTER='Nets 99(99.00%) 1(1.00%) 0(0.00%) 100\nPorts 10(100.00%) 0(0.00%) 0(0.00%) 10\nPins 990(99.00%) 10(1.00%) 0(0.00%) 1000\n'
POWER='Cell Internal Power = 40 mW\nNet Switching Power = 1000 uW\nTotal Dynamic Power = 41 mW\nCell Leakage Power = 200 uW\n'


class NativePowerTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'source'; out=root/'mapped'; tools=out/'tools'; base=root/'base/mapped'
        for p in (source,tools,base): p.mkdir(parents=True,exist_ok=True)
        native=base/'system_name_map.tcl'; native.write_text('SAIF name mapping file\ncreated using Synopsys Power Compiler\ndesign e203_cpu_top\nport inspect_pc[31]\noname Bs:inspect_pc Bd:31\n')
        (source/'SourceNameMap.tcl').write_bytes(native.read_bytes())
        (base/'saif_map_manual.txt').write_text('saif_map [-read_map filename]')
        sdc=root/'view.sdc'; sdc.write_text('create_clock -period 6.666667 [get_ports clk]\n')
        paths={'name_map':str(native),'ddc':str(base/'candidate.ddc'),'sdc':str(sdc)}
        record={'inputs':{},'paths':paths,'task_run':str(root/'original_tasks'),'tasks':{}}
        for name,cycles in (('ff1',332354),('encoder',1485719)):
            case=source/name; case.mkdir()
            (case/'saif_hierarchy.rpt').write_text('Report: saif\n-hierarchy\n'+BEFORE)
            (case/'RawUnknowns.json').write_text('RAW UNKNOWN FIXTURE')
            (case/'read_saif_manual.txt').write_text('read_saif [-map_names] [-auto_map_names]')
            record['tasks'][name]={'cycles':cycles,'duration_seconds':cycles*6.667e-9,'TX_nonzero_entries':1}
        (source/'Inputs.json').write_text(json.dumps(record))
        (source/'PowerPaths.json').write_text(json.dumps(paths))
        (source/'SystemPowerSummary.json').write_text(json.dumps({'tasks':{name:{'total_w':.04} for name in ('ff1','encoder')}}))
        files=[p for p in source.rglob('*') if p.is_file()]
        (source/'MANIFEST.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(source).as_posix()+'\n' for p in files))
        return source,out,tools,base,sdc

    def test_native_map_rerun_retains_originals_and_archives_global_comparison(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory); source,out,tools,base,sdc=self.fixture(root)
            before={p:p.read_bytes() for p in source.rglob('*') if p.is_file()}
            prepare(source,out,tools)
            record=json.loads((out/'Inputs.json').read_text())
            self.assertEqual(record['baseline_global_coverage']['ff1']['pins']['user']['percent'],80)
            for name in ('ff1','encoder'):
                case=out/name
                (case/'tool_status.txt').write_text('NETLIST: UNCHANGED\nSAIF_SCOPE: SharedTest/Cpu\nMAPPING_MODE: NATIVE_SYNTHESIS_MAP_READ_SAIF_MAP_NAMES\nEXTERNAL_NAME_MAP: LOADED_WITH_SAIF_MAP_READ_MAP\n')
                (case/'dc.log').write_text('SYSTEM_POWER_REPORT_COMPLETE: FIXTURE\n')
                (case/'power_view.sdc').write_bytes(sdc.read_bytes())
                (case/'power.rpt').write_text(POWER)
                (case/'saif_coverage.rpt').write_text(BEFORE)
                (case/'saif_hierarchy.rpt').write_text('Report: saif\n-hierarchy\n'+AFTER)
                (case/'private_sram_power.rpt').write_text('Totals (56 cells) 3.322mW 4.717uW 3.326mW (100%) 101.690uW\n')
                for filename in ('shared_itcm_power.rpt','shared_dtcm_power.rpt'):
                    (case/filename).write_text('Totals (32 cells) 5mW 0.1mW 5.1mW (100%) 20uW\n')
            finish(out)
            comparison=json.loads((out/'MappedPowerComparison.json').read_text())
            self.assertEqual(comparison['ff1']['coverage']['pins']['extra_user_annotated'],190)
            summary=json.loads((out/'SystemPowerSummary.json').read_text())
            self.assertEqual(summary['tasks']['ff1']['coverage']['pins']['user']['percent'],99)
            self.assertEqual(summary['tasks']['ff1']['top_only_coverage']['pins']['user']['percent'],80)
            with tarfile.open(out/'SystemPowerReports.partial.tar.gz') as archive:
                self.assertIn('MappedPowerComparison.json',archive.getnames())
            for path,content in before.items(): self.assertEqual(path.read_bytes(),content)
            (base/'system_name_map.tcl').write_text('CHANGED')
            with self.assertRaisesRegex(ValueError,'Frozen input changed'): finish(out)

    def test_tcl_mapping_scripts_are_not_treated_as_native_mapping_data(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            source,out,tools,base,sdc=self.fixture(Path(directory))
            (base/'system_name_map.tcl').write_text('set_rtl_to_gate_name -rtl a -gate b\n')
            with self.assertRaisesRegex(ValueError,'Expected original native'): prepare(source,out,tools)


if __name__=='__main__': unittest.main()
