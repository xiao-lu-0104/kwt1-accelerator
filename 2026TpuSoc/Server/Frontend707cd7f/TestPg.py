"""Current-PG source/geometry/report guards and orchestration with fake ICC2 only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from BuildPg import build_files


def geometry(d):
    macros=['instance\tref\tx1\ty1\tx2\ty2'];pins=['instance\tref\tpin\tshape\tlayers\tx1\ty1\tx2\ty2\tstatus']
    for i in range(120):
        ref='RAMSP1024X16' if i<56 else 'RAMSP4096X16';name='Macro'+str(i);x=(i%12)*150;y=(i//12)*150
        macros.append('%s\t%s\t%d\t%d\t%d\t%d'%(name,ref,x,y,x+82,y+111))
        for j,pin in enumerate(('VDDCE','VDDPE','VSSE')):
            pins.append('%s\t%s\t%s\tS\tM4\t%s\t%s\t%s\t%s\tSHAPE_CAPTURED'%(name,ref,pin,x+1+j*.21,y+1,x+1+j*.21+.11,y+110))
    (d/'macros.tsv').write_text('\n'.join(macros)+'\n');(d/'MacroPgGeometry.tsv').write_text('\n'.join(pins)+'\n')


def connection(floating=0):
    return '\n'.join('Net '+net+'\n'+'\n'.join('Number of floating '+kind+': '+str(floating if kind=='hard macros' else 0)
            for kind in ('wires','vias','std cells','hard macros','I/O pads','I/O terminals','hierarchical blocks')) for net in ('VDD','VSS'))


class Pg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        for n,b in build_files().items():
            p=cls.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        sys.path.insert(0,str(cls.root/'tools'))
        spec=importlib.util.spec_from_file_location('CurrentPgUnderTest',cls.root/'tools/PgFlow.py')
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.root/'tools'));cls.temp.cleanup()

    def test_complete_native_zero_reports(self):
        self.assertTrue(self.module.connectivity_result(connection())['clean'])
        self.assertTrue(self.module.drc_result('Total number of DRC errors: 0')['clean'])

    def test_floating_macros_cannot_pass(self):
        self.assertFalse(self.module.connectivity_result(connection(120))['clean'])

    def test_partial_unknown_or_error_reports_cannot_pass(self):
        self.assertFalse(self.module.connectivity_result(connection().split('Net VSS')[0])['clean'])
        self.assertFalse(self.module.drc_result('Command executed successfully')['clean'])
        self.assertFalse(self.module.drc_result('Error: failed\nTotal number of DRC errors: 0')['clean'])

    def test_old_939_drc_is_not_clean(self):
        self.assertFalse(self.module.drc_result('Total number of DRC errors: 939')['clean'])

    def test_per_macro_geometry_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);geometry(d)
            self.assertEqual(self.module.validate_geometry(d)['shape_count'],360)
            p=d/'MacroPgGeometry.tsv';p.write_text('\n'.join(p.read_text().splitlines()[:-1])+'\n')
            with self.assertRaises(ValueError):self.module.validate_geometry(d)

    def test_wrong_macro_pin_layer_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);geometry(d);p=d/'MacroPgGeometry.tsv';p.write_text(p.read_text().replace('\tM4\t','\tM5\t',1))
            with self.assertRaises(ValueError):self.module.validate_geometry(d)

    def case(self,mode,files_builder=build_files,prepare_hook=None,fake_transform=None):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);soc=home/'soc';soc.mkdir();source=soc/'tpusoc_initial_pr_v2_20261110_707cd7f_fixture';source.mkdir()
            out=soc/'new_pg_fixture';out.mkdir()
            for n,b in files_builder().items():
                p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            stage=source/'design';stage.mkdir();geometry(stage)
            lib=stage/'system_707cd7f.nlib';lib.mkdir();(lib/'design.dat').write_text('ORIGINAL_GROUPED_IO_DESIGN')
            (stage/'DieBoundary.txt').write_text('0 0 2100 2100')
            ports=['clk','rst_n']+['mem_icb_cmd_wdata['+str(i)+']' for i in range(128)]
            (stage/'PortInventory.tsv').write_text('port\tdirection\n'+''.join(p+'\tin\n' for p in ports))
            from PinPlan import plan,validate
            data=plan(stage)
            header='port\tterminal\tx1\ty1\tx2\ty2\tlayers\n'
            body=''.join('%s\t%s\t%s\t%s\t%s\t%s\t%s\n'%(p['port'],p['port'],p['x']-.035,p['y']-.035,p['x']+.035,p['y']+.035,p['layer']) for p in data['pins'])
            (stage/'PortTerminalGeometry.tsv').write_text(header+body);io=validate(stage)
            (source/'inputs').mkdir();(source/'inputs/candidate.v').write_text('CURRENT_707_NETLIST');(source/'inputs/candidate.sdc').write_text('CURRENT_SDC')
            sha=self.module.sha;refs={}
            for label in ('rvt','private','shared'):
                p=source/('library_'+label)/(label+'.ndm');p.mkdir(parents=True);(p/'ref').write_text(label)
                refs['/historical_reference/'+label+'.ndm']=self.module.tree(p)
            record={'source_commit':self.module.REV,'inputs':{},'reference_snapshots':refs,'expected_serialized_period_ns':'6.66667',
                    'design_sdc_sha256':sha(source/'inputs/candidate.sdc')}
            (source/'NewPrInputs.json').write_text(json.dumps(record))
            (source/'NewPrSummary.json').write_text(json.dumps({'source_commit':self.module.REV,'result':'NEW_707CD7F_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING',
                'original_inputs_unchanged':True,'io_validation':io,'design_library':str(lib),'design_netlist_sha256':sha(source/'inputs/candidate.v')}))
            (source/'tool.txt').write_text('FROZEN_INITIAL_PACKAGE_TOOL');(source/'PACKAGE.sha256').write_text(sha(source/'tool.txt')+'  tool.txt\n')
            cfg=json.loads((out/'Config.json').read_text());cfg['initial_package_sha256']=sha(source/'PACKAGE.sha256');(out/'Config.json').write_text(json.dumps(cfg))
            fake=home/'fake_icc';fake_code='''#!/usr/bin/env python3
from pathlib import Path
import json,os,re
p=Path.cwd();phase=re.search(r'set Phase \\{([^}]+)\\}',(p/'PgConfig.tcl').read_text()).group(1)
lib=p/'system_707cd7f.nlib';(lib/'design.dat').write_text('NEW_COPY_'+phase)
if phase in ('legalize','pg_core'):
    (p/('legalized.def' if phase=='legalize' else 'pg_complete.def')).write_text('NEW_PG_DEF')
    data=json.loads((p/'PinPlan.json').read_text());rows=['port\\tterminal\\tx1\\ty1\\tx2\\ty2\\tlayers']
    for pin in data['pins']:
        x,y=pin['x'],pin['y']
        if os.environ['MODE']=='bad_io':x+=10
        rows.append('%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s'%(pin['port'],pin['port'],x-.035,y-.035,x+.035,y+.035,pin['layer']))
    (p/'PortTerminalGeometry.tsv').write_text('\\n'.join(rows)+'\\n')
    print('NEW_707CD7F_PG_PHASE_COMPLETE '+phase)
else:
    if phase=='connectivity':
        text='\\n'.join('Net '+net+'\\n'+'\\n'.join('Number of floating '+kind+': '+str(120 if os.environ['MODE']=='floating' and kind=='hard macros' else 0) for kind in ('wires','vias','std cells','hard macros','I/O pads','I/O terminals','hierarchical blocks')) for net in ('VDD','VSS'))
    else:text='Total number of DRC errors: '+('939' if os.environ['MODE']=='drc' else '0')
    (p/(phase+'.rpt')).write_text(text);print('NEW_707CD7F_PG_CHECK_EXECUTED '+phase)
'''
            if fake_transform:fake_code=fake_transform(fake_code)
            fake.write_text(fake_code);fake.chmod(0o755)
            physical=soc/'tpusoc_icc2_start_20261108_mTq1LE';physical.mkdir();(physical/'PrInputs.json').write_text(json.dumps({'icc2':str(fake),'icc2_flag':'-file'}))
            if prepare_hook:prepare_hook(self,source,out,soc,mode)
            if mode=='changed_source':(source/'inputs/candidate.v').write_text('WRONG_SOURCE')
            if mode=='prior':
                prior=soc/'tpusoc_pg_20261110_707cd7f_existing';prior.mkdir()
                (prior/'PgInputs.json').write_text(json.dumps({'source_run':str(source)}))
            originals={str(p):sha(p) for d in soc.iterdir() if d!=out for p in d.rglob('*') if p.is_file()}
            result=subprocess.run(['python3',str(out/'tools/PgFlow.py'),str(out)],env=dict(os.environ,HOME=str(home),MODE=mode),capture_output=True,text=True,timeout=30)
            self.assertTrue(all(sha(Path(p))==h for p,h in originals.items()),result.stdout+result.stderr)
            if mode in ('floating','drc'):
                self.assertTrue((out/'pg_core/pg_complete.def').is_file())
                self.assertTrue((out/'drc/drc.rpt').is_file(),'DRC must still run when connectivity has violations')
                self.assertFalse(json.loads((out/'NewPgSummary.json').read_text())['checks']['connectivity' if mode=='floating' else 'drc']['clean'])
            if mode=='bad_io':self.assertFalse((out/'pg_core').exists())
            if mode in ('changed_source','prior'):self.assertFalse((out/'legalize').exists())
            return result.returncode,result.stdout+result.stderr

    def test_full_flow_and_source_unchanged(self):
        c,s=self.case('ok');self.assertEqual(c,0,s)
    def test_floating_result_retains_pg_and_runs_drc(self):
        c,s=self.case('floating');self.assertNotEqual(c,0,s)
    def test_actual_drc_violations_are_not_exit0_acceptance(self):
        c,s=self.case('drc');self.assertNotEqual(c,0,s)
    def test_bad_io_stops_before_pg(self):
        c,s=self.case('bad_io');self.assertNotEqual(c,0,s)
    def test_changed_source_stops_before_native(self):
        c,s=self.case('changed_source');self.assertNotEqual(c,0,s)
    def test_prior_attempt_requires_checkpoint_review(self):
        c,s=self.case('prior');self.assertNotEqual(c,0,s);self.assertIn('PG attempt for this source already exists',s)


if __name__=='__main__':unittest.main()
