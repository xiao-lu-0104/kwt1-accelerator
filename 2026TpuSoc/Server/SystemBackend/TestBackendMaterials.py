"""Raw-material packaging must retain provenance, revised firmware and limitations."""
import contextlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from BackendMaterials import pack,coverage_status
from Prepare import sha


def fixture(root):
    source=root/'power'; out=root/'out'; tools=out/'tools'; task=root/'tasks'; sim=root/'original_sim'
    base=root/'base'; clock=root/'clock'; bundle=root/'bundle'
    for path in (source,tools,task/'firmware/Sw',task/'firmware/BuildEvidence',sim/'tools',base/'mapped',base/'tools',clock,bundle/'Sw'):
        path.mkdir(parents=True,exist_ok=True)
    def write(path,text): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
    write(bundle/'Sw/SharedStart.S','ORIGINAL BOOT')
    write(bundle/'Firmware.hex','OLD IMAGE'); write(bundle/'Firmware.bin','OLD BINARY')
    paths=[p for p in bundle.rglob('*') if p.is_file()]
    write(bundle/'MANIFEST.sha256',''.join(sha(p)+'  '+p.relative_to(bundle).as_posix()+'\n' for p in paths))
    write(task/'Bundle.txt',str(bundle))
    revised=task/'firmware'; write(revised/'Sw/SharedStart.S','REVISED BOOT')
    write(revised/'BuildEvidence/Firmware.hex','REVISED IMAGE')
    write(revised/'BuildEvidence/Shared.bin','REVISED BINARY')
    write(revised/'BuildEvidence/BootFix.json',json.dumps({'fixed_hex_sha256':sha(revised/'BuildEvidence/Firmware.hex')}))
    for name in ('PhysicalSharedTest.sv','SharedTcmGuard.sv','SystemActivity.sv','EffectiveDataGuard.sv','GateResetInventory.sv','IcbMirror.sv','Task.f'):
        write(sim/name,'ORIGINAL '+name)
    write(sim/'tools/TcmInitializer.sv','ORIGINAL INITIALIZER')
    write(base/'tools/TcmMacro.sv','PHYSICAL MACRO WRAPPER')
    for name in ('candidate.v','candidate.ddc'): write(base/'mapped'/name,'ORIGINAL '+name)
    for path in (base/'ExistingMaterials.partial.tar.gz',base/'SystemMappingReports.partial.tar.gz',clock/'ClockPortReports.partial.tar.gz',source/'SystemPowerReports.partial.tar.gz'):
        write(path,'ARCHIVE FIXTURE')
    write(clock/'clock_ports_corrected.sdc','VERIFIED CLOCK VIEW')
    write(clock/'AreaBreakdown.json',json.dumps({'accelerator_budget_area_um2':703272.383184,'system_area_um2':2495814.810768,'shared_capacity_bytes':524288}))
    write(clock/'ClockPortSummary.json',json.dumps({'SETUP_STATUS':'PASS','HOLD_STATUS':'PASS','SETUP_WNS_NS':'.00191832','HOLD_WNS_NS':'.0000830591'}))
    write(task/'Inputs.json',json.dumps({'inputs':{},'source':str(base),'review':str(clock),'original_task_run':str(sim)}))
    evidence={}; power_tasks={}
    cov={'total':100,'user':{'count':80,'percent':80},'propagated':{'count':15,'percent':15},'default':{'count':5,'percent':5}}
    for name in ('ff1','encoder'):
        for filename in ('run.log','task.saif','Activity.json'):
            path=task/name/filename; write(path,'VALIDATED '+name+' '+filename); evidence[str(path)]=sha(path)
        write(source/name/'tool_status.txt','NAME_MAPPING_LIFECYCLE: STARTED_BEFORE_DDC\n')
        write(source/name/'RawUnknowns.json',json.dumps({'unknown':[{'scope':'SharedTest/Cpu/u_e203_cpu/u_e203_core','signal':'idle'}]}))
        write(source/name/'saif_missing.rpt','List of Non-annotated nets :\nexample\n')
        power_tasks[name]={'cycles':332354,'dynamic_w':.0338795,'leakage_w':.0003817452,'total_w':.0342612452,
            'task_energy_j':.0000759162082,'coverage':{kind:cov for kind in ('nets','ports','pins')},
            'regional_coverage':{'cpu_core':{kind:cov for kind in ('nets','ports','pins')}},'TX_nonzero_entries':1}
    write(task/'SystemActivitySummary.json',json.dumps({'both_tasks_use_same_repaired_firmware':True,'evidence_sha256':evidence}))
    write(source/'Inputs.json',json.dumps({'inputs':{},'require_active_mapping':True,'task_run':str(task),'paths':{}}))
    write(source/'SystemPowerSummary.json',json.dumps({'tasks':power_tasks,'scope':'e203_cpu_top; external peripherals excluded','method':'PRELAYOUT FIXTURE'}))
    paths=[p for p in source.rglob('*') if p.is_file()]
    write(source/'MANIFEST.sha256',''.join(sha(p)+'  '+p.relative_to(source).as_posix()+'\n' for p in paths))
    return source,out,tools,bundle,task


class BackendMaterialTests(unittest.TestCase):
    def test_default_activity_is_separate_from_observed_and_propagated(self):
        group={'total':100,'user':{'count':80},'propagated':{'count':15},'default':{'count':5}}
        result=coverage_status(group)
        self.assertEqual(result['user_plus_propagated_percent'],95)
        self.assertEqual(result['default'],5)
        empty={'total':0,'user':{'count':0},'propagated':{'count':0},'default':{'count':0}}
        self.assertIsNone(coverage_status(empty)['user_plus_propagated_percent'])
        with self.assertRaises(ValueError): coverage_status({**group,'total':99})

    def test_archive_contains_current_firmware_without_modifying_original_bundle(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            source,out,tools,bundle,task=fixture(Path(directory))
            originals={p:p.read_bytes() for p in Path(directory).rglob('*') if p.is_file()}
            pack(source,out,tools)
            material=out/'BackendRawMaterials'
            self.assertEqual((material/'Sources/Team/Sw/SharedStart.S').read_text(),'REVISED BOOT')
            self.assertEqual((material/'Sources/Team/Firmware.hex').read_text(),'REVISED IMAGE')
            self.assertEqual((material/'Sources/Team/Firmware.bin').read_text(),'REVISED BINARY')
            self.assertEqual((material/'Simulation/SharedTcmGuard.sv').read_text(),'ORIGINAL SharedTcmGuard.sv')
            result=json.loads((material/'BackendMaterialsSummary.json').read_text())
            self.assertTrue(result['limitations'])
            self.assertIn('not a clean portable reproduction claim',(material/'README.md').read_text())
            with tarfile.open(out/'BackendRawMaterials.partial.tar.gz') as archive:
                self.assertIn('BackendRawMaterials/MANIFEST.sha256',archive.getnames())
                self.assertFalse(any(name.endswith(('.lib','.db')) for name in archive.getnames()))
            for path,data in originals.items(): self.assertEqual(path.read_bytes(),data)

    def test_changed_bundle_cannot_be_silently_packaged(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            source,out,tools,bundle,task=fixture(Path(directory))
            (bundle/'Sw/SharedStart.S').write_text('UNEXPECTED CHANGE')
            with self.assertRaisesRegex(ValueError,'Original power report changed'): pack(source,out,tools)


if __name__=='__main__': unittest.main()
