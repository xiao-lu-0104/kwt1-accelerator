"""Keep hierarchy coverage tables distinct and preserve completed power evidence."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from Prepare import sha
from PowerCoverage import coverage,coverage_tables
from SystemPowerReview import run

TABLE='Nets 99(99.00%) 1(1.00%) 0(0.00%) 100\nPorts 10(100.00%) 0(0.00%) 0(0.00%) 10\nPins 990(99.00%) 10(1.00%) 0(0.00%) 1000\n'


class PowerReviewTests(unittest.TestCase):
    def test_multiple_hierarchy_tables_never_overwrite_previous_rows(self):
        text='Report: saif\nDesign: e203_cpu_top\n'+TABLE+'Instance: small_child\n'+TABLE.replace('1000','2000').replace('990(','1990(')
        tables=coverage_tables(text)
        self.assertEqual(len(tables),2)
        self.assertEqual(tables[0]['objects']['pins']['total'],1000)
        self.assertEqual(tables[1]['objects']['pins']['total'],2000)
        self.assertIn('Design: e203_cpu_top',tables[0]['context'])
        with self.assertRaisesRegex(ValueError,'Multiple'): coverage(text)
        self.assertEqual(coverage(TABLE)['nets']['total'],100)
        with self.assertRaisesRegex(ValueError,'Incomplete'): coverage_tables(TABLE.split('Pins')[0])

    def test_existing_reports_estimates_and_maps_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'power'; out=root/'review'; tools=out/'tools'; base=root/'base/mapped'
            for path in (source,tools,base): path.mkdir(parents=True,exist_ok=True)
            tasks={}
            for name in ('ff1','encoder'):
                case=source/name; case.mkdir()
                (case/'saif_coverage.rpt').write_text('Design: e203_cpu_top\n'+TABLE+'Instance: small_child\n'+TABLE)
                (case/'saif_hierarchy.rpt').write_text('Report: saif -hierarchy\n'+TABLE)
                (case/'saif_missing.rpt').write_text('Report: saif -missing -hierarchy\n'+TABLE)
                (case/'RawUnknowns.json').write_text(json.dumps({'unknown':[{'scope':'SharedTest/Cpu/u_e203_cpu/u_e203_core',
                    'signal':'unused','TX_fraction':1,'kind':'NET'}]}))
                (case/'read_saif_help.txt').write_text('read_saif -input -instance_name')
                (case/'read_saif_manual.txt').write_text('read_saif\n-map_names\nUse saved mapping\n')
                tasks[name]={'total_w':.034,'task_energy_j':.000075,'coverage':{'OLD':'LOCAL_TABLE_FIXTURE'}}
            (source/'Inputs.json').write_text(json.dumps({'inputs':{},'paths':{'ddc':str(base/'candidate.ddc')}}))
            (source/'SourceNameMap.tcl').write_text('# fixture generated mapping\nset_rtl_to_gate_name -rtl {old} -gate {new}\n')
            (source/'SystemPowerSummary.json').write_text(json.dumps({'tasks':tasks}))
            files=[p for p in source.rglob('*') if p.is_file()]
            (source/'MANIFEST.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(source).as_posix()+'\n' for p in files))
            before={p:p.read_bytes() for p in source.rglob('*') if p.is_file()}
            with contextlib.redirect_stdout(io.StringIO()): run(source,out,tools)
            result=json.loads((out/'SystemPowerReview.json').read_text())
            self.assertEqual(result['tasks']['ff1']['coverage_reports']['saif_coverage.rpt']['table_count'],2)
            self.assertEqual(result['name_map']['command_counts']['set_rtl_to_gate_name'],1)
            self.assertEqual(before,{p:p.read_bytes() for p in source.rglob('*') if p.is_file()})
            (source/'ff1/saif_coverage.rpt').write_text('ALTERED')
            with self.assertRaisesRegex(ValueError,'Original system report changed'),contextlib.redirect_stdout(io.StringIO()): run(source,out,tools)


if __name__=='__main__': unittest.main()
