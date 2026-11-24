"""Validate shared-TCM contracts, source selection and frozen-accelerator mapping guards."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch
from Prepare import platform_files,sha,archive,freeze_prepared_outputs,check
from RecoverSummary import recovery_record
from Summarize import contract_pass,mapped_summary

HERE=Path(__file__).resolve().parent


class SystemBaseTests(unittest.TestCase):
    def test_preparation_freezes_artifacts_not_live_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            names=('Sources.tcl','frozen_accelerator.v','OriginalRam.txt','SharedModel.txt',
                'SharedLib.txt','StdDb.txt','SpDb.txt','ExistingMaterials.partial.tar.gz','ExistingMaterials.sha256')
            for name in names: (out/name).write_text(name)
            (out/'prepare.log').write_text('still writing')
            inputs={}; freeze_prepared_outputs(out,inputs)
            (out/'prepare.log').write_text('now finished')
            check({'inputs':inputs})
            self.assertEqual(len(inputs),len(names))

    def test_recovery_verifies_prefix_and_keeps_other_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory); tools=out/'recovery_tools'; tools.mkdir()
            (tools/'tool.py').write_text('verified repair')
            mapped=out/'mapped'; mapped.mkdir()
            (mapped/'status.txt').write_text('COMPLETE\n')
            (mapped/'dc.log').write_text('SYSTEM_MAPPING_REPORTS_COMPLETE: fixture\n')
            frozen=out/'frozen_accelerator.v'; frozen.write_text('unchanged candidate')
            log=out/'prepare.log'; prefix=b'SYSTEM_PREP: fixture\n'; log.write_bytes(prefix)
            record={'inputs':{str(log):sha(log),str(frozen):sha(frozen)}}
            original=out/'SystemBaseInputs.json'; original.write_text(json.dumps(record))
            original_bytes=original.read_bytes()
            log.write_bytes(prefix+b'SYSTEM_PREP_COMPLETE: sources=160 elapsed_seconds=47.878\n')
            recovered=recovery_record(out,tools); check(recovered)
            self.assertEqual(original.read_bytes(),original_bytes)
            self.assertEqual(recovered['recovery']['prefix_bytes'],len(prefix))
            frozen.write_text('changed candidate')
            with self.assertRaisesRegex(ValueError,'Frozen input changed'): recovery_record(out,tools)
            frozen.write_text('unchanged candidate')
            log.write_bytes(b'changed prefix\nSYSTEM_PREP_COMPLETE: sources=160 elapsed_seconds=47.878\n')
            with self.assertRaisesRegex(ValueError,'original frozen prefix'): recovery_record(out,tools)
            log.write_bytes(prefix+b'SYSTEM_PREP_COMPLETE: sources=160 elapsed_seconds=47.878\nunexpected\n')
            with self.assertRaisesRegex(ValueError,'Unexpected appended'): recovery_record(out,tools)

    def test_recovery_creates_archive_without_eda_and_preserves_failed_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory); (out/'contract').mkdir(); (out/'mapped').mkdir()
            (out/'prepare.log').write_text('original log\n')
            (out/'Sources.tcl').write_text('original sources')
            (out/'frozen_accelerator.v').write_text('original candidate')
            record={'inputs':{str(out/name):sha(out/name) for name in ('prepare.log','Sources.tcl','frozen_accelerator.v')}}
            original=out/'SystemBaseInputs.json'; original.write_text(json.dumps(record)); before=original.read_bytes()
            with (out/'prepare.log').open('ab') as stream: stream.write(b'SYSTEM_PREP_COMPLETE: sources=160 elapsed_seconds=47.878\n')
            (out/'contract/status.txt').write_text('PASS\n')
            (out/'contract/run.log').write_text('''PASS TCM_PORT_CONTRACT: DW=64 DP=32768 banks=8 macros=32 checks=96; details
PASS TCM_PORT_CONTRACT: DW=32 DP=65536 banks=16 macros=32 checks=128; details
PASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros; details
''')
            (out/'mapped/status.txt').write_text('COMPLETE\n')
            (out/'mapped/dc.log').write_text('SYSTEM_MAPPING_REPORTS_COMPLETE: fixture\n')
            (out/'mapped/summary.txt').write_text('''TOP: e203_cpu_top
FROZEN_ACCELERATOR: UNCHANGED
PRIVATE_SRAM_COUNT: 56
SHARED_SRAM_COUNT: 64
SHARED_CAPACITY_BYTES: 524288
SETUP_WNS_NS: -0.1
HOLD_WNS_NS: 0.01
SYSTEM_LIBRARY_AREA_UM2: 2000000
SETUP_STATUS: FAIL
HOLD_STATUS: PASS
''')
            process=subprocess.run([sys.executable,'-B',str(HERE/'RecoverSummary.py'),str(out)],capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            result=json.loads((out/'SystemBaseSummary.json').read_text())
            self.assertEqual(result['mapped']['SETUP_STATUS'],'FAIL')
            self.assertEqual(original.read_bytes(),before)
            check(json.loads((out/'SystemBaseRecoveryInputs.json').read_text()))
            with tarfile.open(out/'SystemMappingReports.partial.tar.gz') as stream:
                self.assertIn('SystemBase/SystemBaseRecoveryInputs.json',stream.getnames())

    def test_raw_archive_retains_original_bytes_and_externalizes_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); out=base/'out'; out.mkdir()
            source=base/'power'; source.mkdir(); bundle=base/'bundle'; bundle.mkdir()
            functional=base/'functional'; (functional/'project').mkdir(parents=True)
            platform=functional/'project/e203_hbirdv2/rtl/e203'; platform.mkdir(parents=True)
            qualification=base/'qualification'; qualification.mkdir()
            original=base/'asic'; (original/'mapped').mkdir(parents=True)
            report=base/'report'; report.mkdir(); inventory=base/'inventory'; inventory.mkdir()
            for task in ('ff1','encoder'):
                (source/task).mkdir(); (qualification/task).mkdir()
                (source/task/'task.saif').write_text('ORIGINAL ACTIVITY '+task)
                (qualification/task/'run.log').write_text('ORIGINAL GUARD '+task)
            (bundle/'owned.sv').write_text('OWN SOURCE')
            (bundle/'MANIFEST.sha256').write_text(sha(bundle/'owned.sv')+'  owned.sv\n')
            (source/'Bundle.txt').write_text(str(bundle))
            (source/'Functional.txt').write_text(str(functional))
            (platform/'e203_cpu_top.v').write_text('PUBLIC CPU')
            (functional/'ff1_normal.log').write_text('ORIGINAL FUNCTIONAL')
            for suffix in ('ddc','v','sdc'): (original/'mapped'/('candidate.'+suffix)).write_text('ORIGINAL '+suffix)
            (report/'summary.txt').write_text('ORIGINAL REPORT')
            std=base/'std.db'; std.write_text('DO NOT ARCHIVE FOUNDRY LIBRARY')
            private=base/'private.db'; private.write_text('DO NOT ARCHIVE SRAM LIBRARY')
            power={'paths':{'original':str(original),'report':str(report),'std_db':str(std),'sram_db':str(private)},'inventory':str(inventory)}
            with patch('Prepare.BUNDLE_MANIFEST',sha(bundle/'MANIFEST.sha256')):
                archive(out,qualification,{},source,power,platform)
            package=out/'ExistingMaterials.partial.tar.gz'
            with tarfile.open(package) as stream:
                names=stream.getnames()
                self.assertFalse(any(name.endswith('.db') for name in names))
                self.assertEqual(stream.extractfile('ExistingMaterials/AcceleratorMapping/candidate.ddc').read(),b'ORIGINAL ddc')
                self.assertEqual(stream.extractfile('ExistingMaterials/TaskPower/ff1/task.saif').read(),b'ORIGINAL ACTIVITY ff1')
                status=stream.extractfile('ExistingMaterials/STATUS.txt').read().decode()
                self.assertIn('PARTIAL',status)
                self.assertIn('complete system activity/power',status)
            self.assertIn(sha(package),(out/'ExistingMaterials.sha256').read_text())

    def test_contract_requires_both_widths_and_rejects_fatal(self):
        text='''PASS TCM_PORT_CONTRACT: DW=64 DP=32768 banks=8 macros=32 checks=96; details
PASS TCM_PORT_CONTRACT: DW=32 DP=65536 banks=16 macros=32 checks=128; details
PASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros; details'''
        self.assertTrue(contract_pass(text))
        self.assertFalse(contract_pass(text.replace('checks=128','checks=127')))
        self.assertFalse(contract_pass(text+'\nFatal: unknown data'))

    def test_source_selection_keeps_original_cpu_and_replaces_only_ram(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'power'; source.mkdir(); audit=root/'audit'; audit.mkdir()
            out=root/'out'; out.mkdir(); tools=root/'tools'; tools.mkdir()
            platform=root/'functional/project/e203_hbirdv2/rtl/e203'; platform.mkdir(parents=True)
            names=['e203_cpu_top.v','sirv_sim_ram.v','sirv_gnrl_ram.v']
            for name in names: (platform/name).write_text('module '+name[:-2]+'; endmodule\n')
            scope={'configuration_modified':False,'cpu_datapath_modified':False,
                'copied_platform_sha256':{n:sha(platform/n) for n in names}}
            (platform.parents[2]/'Scope.json').write_text(json.dumps(scope))
            (audit/'SystemPowerPreparation.json').write_text(json.dumps({'platform_source':str(platform)}))
            (source/'Task.f').write_text('+incdir+'+str(platform)+'\n'+'\n'.join(str(platform/n) for n in names)+'\n')
            candidate=source/'candidate.v'; candidate.write_text('frozen fixture')
            real_sha=sha
            def digest(path):
                return 'b366417d57d6251f13a827933288886637b61071472d391b121a7341fa2ea75e' if path==candidate else real_sha(path)
            with patch('Prepare.sha',side_effect=digest): platform_files(source,audit,tools,out)
            text=(out/'Sources.tcl').read_text()
            self.assertIn(str(platform/'e203_cpu_top.v'),text)
            self.assertIn(str(platform/'sirv_sim_ram.v'),text)
            self.assertNotIn(str(platform/'sirv_gnrl_ram.v'),text)
            self.assertIn(str(tools/'TcmMacro.sv'),text)
            (platform/'e203_cpu_top.v').write_text('changed')
            with self.assertRaisesRegex(ValueError,'snapshot changed'):
                platform_files(source,audit,tools,out)

    def test_mapping_summary_cannot_hide_failed_timing(self):
        text='''TOP: e203_cpu_top
FROZEN_ACCELERATOR: UNCHANGED
PRIVATE_SRAM_COUNT: 56
SHARED_SRAM_COUNT: 64
SHARED_CAPACITY_BYTES: 524288
SETUP_WNS_NS: -0.1
HOLD_WNS_NS: 0.01
SYSTEM_LIBRARY_AREA_UM2: 2000000
SETUP_STATUS: FAIL
HOLD_STATUS: PASS'''
        self.assertEqual(mapped_summary(text)['SETUP_STATUS'],'FAIL')
        with self.assertRaisesRegex(ValueError,'status/slack mismatch'):
            mapped_summary(text.replace('SETUP_STATUS: FAIL','SETUP_STATUS: PASS'))
        with self.assertRaisesRegex(ValueError,'memory accounting'):
            mapped_summary(text.replace('SHARED_SRAM_COUNT: 64','SHARED_SRAM_COUNT: 63'))

    def test_system_tcl_freezes_accelerator_and_enforces_macro_counts(self):
        import tkinter
        for mode,expected in (('pass',0),('changed_accelerator',1),('wrong_macros',1),('hold_fail',0)):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory); out=root/'mapped'; out.mkdir(); tools=root/'tools'; tools.mkdir()
                shutil.copy2(HERE.parent/'Backend/AsicCommon.tcl',tools/'AsicCommon.tcl')
                (root/'Sources.tcl').write_text('set Sources {}; set Includes {}\n')
                interp=tkinter.Tcl(); interp.setvar('Mode',mode)
                interp.setvar('env(TPU_SYSTEM_OUT)',str(out)); interp.setvar('env(TPU_SYSTEM_TOOLS)',str(tools))
                for key in ('TPU_STDCELL_DB','TPU_SRAM_DB','TPU_SYSTEM_DB'): interp.setvar('env('+key+')',key)
                interp.eval(r'''
set Compiled 0
set search_path {}
set Private {}; set Shared {}; set Leaf {}; set References [dict create]
for {set I 0} {$I<1001} {incr I} {
set Name u_e203_cpu/u_e203_nice_core/U$I
lappend Leaf $Name; dict set References $Name DQV0_12TR40
}
for {set I 0} {$I<56} {incr I} {
set Name u_e203_cpu/u_e203_nice_core/Sram/M$I
lappend Private $Name; lappend Leaf $Name; dict set References $Name RAMSP1024X16
}
for {set I 0} {$I<64} {incr I} {
set Name u_e203_srams/Bank$I
lappend Shared $Name; lappend Leaf $Name; dict set References $Name RAMSP4096X16
}
proc exit {code} {set ::TestExit $code; error TEST_EXIT}
proc foreach_in_collection {variable objects body} {
foreach item $objects {uplevel 1 [list set $variable $item]; uplevel 1 $body}
}
proc get_cells {args} {
if {[lsearch -exact $args -filter]>=0} {
set filter [lindex $args [expr {[lsearch -exact $args -filter]+1}]]
if {$filter eq "is_hierarchical == false"} {return $::Leaf}
if {$filter eq "ref_name == RAMSP1024X16"} {return $::Private}
if {$filter eq "ref_name == RAMSP4096X16"} {
if {$::Mode eq "wrong_macros"} {return [lrange $::Shared 1 end]}
return $::Shared
}
error "Unexpected filter $filter"
}
return u_e203_cpu/u_e203_nice_core
}
proc get_attribute {object attribute} {
if {$attribute eq "ref_name"} {
if {$::Mode eq "changed_accelerator" && $::Compiled && $object eq "u_e203_cpu/u_e203_nice_core/U0"} {return OTHER}
return [dict get $::References $object]
}
if {$attribute eq "area"} {return 10.0}
if {$attribute eq "slack"} {
if {$object eq "min" && $::Mode eq "hold_fail"} {return -0.05}
return 0.2
}
error "Unexpected attribute $attribute"
}
proc sizeof_collection {objects} {return [llength $objects]}
proc get_object_name {object} {return $object}
proc get_lib_cells {args} {return LIBCELL}
proc all_inputs {} {return {clk rst_n command}}
proc all_outputs {} {return {response}}
proc all_clocks {} {return CoreClock}
proc get_ports {port} {return $port}
proc get_timing_paths {args} {return [lindex $args 1]}
foreach name {define_design_lib set_app_var elaborate current_design set_dont_touch create_clock set_clock_uncertainty set_clock_transition set_input_delay set_input_transition set_output_delay set_load set_fix_hold} {
proc $name {args} {}
}
proc set_false_path {args} {error "Unexpected timing cut"}
proc set_multicycle_path {args} {error "Unexpected multicycle"}
proc analyze {args} {return 1}
proc link {} {return 1}
proc compile_ultra {args} {set ::Compiled 1; return 1}
proc compile {args} {return 1}
proc WriteFile {name text} {set F [open $name w]; puts $F $text; close $F}
proc write {args} {WriteFile [lindex $args end] MAPPED}
proc write_sdc {args} {WriteFile [lindex $args end] CONSTRAINTS}
proc saif_map {args} {
if {[lindex $args 0] eq "-write_map"} {WriteFile [lindex $args 1] MAP}
}
foreach name {report_area report_reference report_units report_qor check_design check_timing report_constraint report_timing} {
proc $name {args} {WriteFile [lindex $args end] REPORT}
}
proc redirect {path body} {uplevel 1 $body; WriteFile $path HELP}
proc help {args} {return HELP}
''')
                original=Path.cwd()
                try:
                    with self.assertRaises(tkinter.TclError): interp.call('source',str(HERE/'System.tcl'))
                    self.assertEqual(int(interp.getvar('TestExit')),expected)
                    if expected==0:
                        data=mapped_summary((out/'summary.txt').read_text())
                        self.assertEqual(data['HOLD_STATUS'],'FAIL' if mode=='hold_fail' else 'PASS')
                finally: os.chdir(original)


if __name__=='__main__': unittest.main()
