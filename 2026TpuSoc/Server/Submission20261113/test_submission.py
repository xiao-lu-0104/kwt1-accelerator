"""Meaningful rejection tests for timing/bus evidence and destructive cleanup."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import evaluate
import flow
import power_summary
import clean_server
import pack


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.task=self.root/'task_0000';self.task.mkdir()
        self.input=bytes(12672);self.params=bytes(33280);self.output=bytes(50688)
        for n,b in [('Input.bin',self.input),('Parameters.bin',self.params),('Expected.bin',self.output)]:
            (self.task/n).write_bytes(b)
        (self.root/'Actual.bin').write_bytes(self.output)
        self.manifest={'source_commit':'newrevision','tasks':[{'id':self.task.name,'input_bytes':len(self.input),
            'parameter_bytes':len(self.params),'output_bytes':len(self.output),'nrmse':.001}]}
        self.events=[{'task':self.task.name,'event':'task_caches_cleared','cycle':0},
                     {'task':self.task.name,'event':'load_begin','cycle':1}]
        cycle=2
        for event,base,payload in [('accepted_load_write',0xa0000000,self.input),
                                   ('accepted_load_write',0xa0010000,self.params),
                                   ('accepted_result_write',0xa0060000,self.output)]:
            for offset in range(0,len(payload),4):
                self.events.append({'task':self.task.name,'event':event,'cycle':cycle,'interface':'platform_sysbus',
                    'width_bits':32,'bytes':4,'address':base+offset,'data':0,'mask':15});cycle+=1
        self.events.append({'task':self.task.name,'event':'final_write_response','cycle':cycle})
        self.evidence={'source_commit':'newrevision','system_bus_width':32,'shared_sram_bytes':524288,
            'mode':'soc_sysbus32','preload_task_weights':False,'clock_hz':150000000,'bus_trace':'BusTrace.jsonl',
            'tasks':[{'id':self.task.name,'cycles':cycle,'protocol_checks_pass':True,'output':'Actual.bin',
                      'input_address':0xa0000000,'parameter_address':0xa0010000,'output_address':0xa0060000}]}
    def tearDown(self):self.temp.cleanup()
    def validate(self,evidence=None):
        evidence=copy.deepcopy(evidence or self.evidence)
        trace=self.root/'BusTrace.jsonl';trace.write_text('\n'.join(json.dumps(e) for e in self.events))
        evidence['bus_trace_sha256']=evaluate.sha(trace)
        evaluate.save(self.root/'RunEvidence.json',evidence)
        return evaluate.validate_evidence(self.root,self.manifest,evidence,'newrevision')
    def test_complete_sysbus_trace(self):
        r=self.validate();self.assertEqual(r['status'],'SOC_PERFORMANCE_TRACE_VALIDATED')
        self.assertEqual(r['cycles'],self.evidence['tasks'][0]['cycles'])
    def test_wide_bus_rejected(self):
        self.evidence['system_bus_width']=128
        with self.assertRaises(ValueError):self.validate()
    def test_preloaded_weights_rejected(self):
        self.evidence['preload_task_weights']=True
        with self.assertRaises(ValueError):self.validate()
    def test_missing_transfer_rejected(self):
        self.events.pop(4)
        with self.assertRaises(ValueError):self.validate()
    def test_wrong_raw_data_rejected(self):
        self.events[3]['data']=17
        with self.assertRaises(ValueError):self.validate()
    def test_wrong_output_rejected(self):
        (self.root/'Actual.bin').write_bytes(b'\x01'+self.output[1:])
        with self.assertRaises(ValueError):self.validate()
    def test_late_timer_rejected(self):
        self.events[1]['cycle']=500
        with self.assertRaises(ValueError):self.validate()
    def test_revision_mismatch_rejected(self):
        self.evidence['source_commit']='oldrevision'
        with self.assertRaises(ValueError):self.validate()
    def test_pending_config_cannot_launch_eda(self):
        with self.assertRaisesRegex(ValueError,'FRONTEND_PENDING'):
            flow.check({'frontend_bound':False})
    def test_power_units_and_missing_units(self):
        text='Cell Internal Power = 3 mW\nNet Switching Power = 2 mW\nTotal Dynamic Power = 5 mW\nCell Leakage Power = 100 uW\n'
        self.assertAlmostEqual(power_summary.power_values(text)['total_w'],.0051)
        with self.assertRaises(ValueError):power_summary.power_values(text.replace('100 uW','100'))
    def test_archive_roundtrip_and_frozen_manifest(self):
        data=pack.frozen({'Rtl/Test.sv':b'module Test;endmodule\n'},'newrevision')
        pack.archive(self.root/'source.tar.gz',data)
        for n,b in data.items():
            p=self.root/'frozen'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        self.assertEqual(evaluate.git_revision(self.root/'frozen'),'newrevision')
        (self.root/'frozen/Rtl/Test.sv').write_text('changed')
        with self.assertRaises(ValueError):evaluate.git_revision(self.root/'frozen')
    def test_cleanup_stops_without_native_cache_check(self):
        cache=self.root/'cache';cache.mkdir();soc=self.root/'soc';soc.mkdir()
        victim=soc/'old';victim.mkdir();(victim/'keep.txt').write_text('old')
        evaluate.save(cache/'Cache.json',{'libraries':[]})
        evaluate.save(cache/'CleanupPlan.json',{'uid':os.getuid() if hasattr(os,'getuid') else 0,
            'soc':str(soc),'cache':str(cache),'cache_manifest_sha256':evaluate.sha(cache/'Cache.json'),'targets':[]})
        if not hasattr(os,'getuid'):self.skipTest('Linux filesystem ownership check')
        with patch.object(clean_server.Path,'home',return_value=self.root):
            with self.assertRaisesRegex(RuntimeError,'probe_cache'):
                clean_server.apply(cache/'CleanupPlan.json')
        self.assertTrue((victim/'keep.txt').is_file())


if __name__=='__main__':unittest.main(verbosity=2)
