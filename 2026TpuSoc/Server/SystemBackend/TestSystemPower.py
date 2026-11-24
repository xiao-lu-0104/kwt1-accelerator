"""Validate system power accounting and the read-only installed Tcl protocol."""
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
import os
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'SharedAsic'))
from SystemPower import parse_power,parse_macro_power,coverage,prepare,finish
from Prepare import sha


class SystemPowerTests(unittest.TestCase):
    def test_collection_preserves_sources_and_rejects_changed_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); task=root/'task'; out=root/'power'; base=root/'base'; review=root/'review'; tools=out/'tools'
            for p in (task,tools,base/'mapped',base/'sram_db',review): p.mkdir(parents=True,exist_ok=True)
            for name in ('std.db','private.db'): (base/name).write_text('EXTERNAL LIBRARY FIXTURE')
            (base/'StdDb.txt').write_text(str(base/'std.db')); (base/'SpDb.txt').write_text(str(base/'private.db'))
            (base/'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db').write_text('EXTERNAL LIBRARY FIXTURE')
            (base/'mapped/candidate.ddc').write_text('ORIGINAL SYSTEM CHECKPOINT FIXTURE')
            (base/'mapped/system_name_map.tcl').write_text('# ORIGINAL MAPPING EVIDENCE')
            (review/'Inputs.json').write_text(json.dumps({'inputs':{}}))
            (review/'MANIFEST.sha256').write_text('')
            (review/'clock_ports_corrected.sdc').write_text('create_clock -name CoreClock -period 6.666667 [get_ports clk]\n')
            (review/'ClockPortSummary.json').write_text('FIXTURE VERIFIED CLOCK VIEW')
            (task/'Inputs.json').write_text(json.dumps({'inputs':{},'source':str(base),'review':str(review)}))
            (tools/'SystemPower.py').write_text('IMMUTABLE TEST HELPER')
            evidence={}; tasks={}
            for name,cycles in (('ff1',332354),('encoder',1485719)):
                case=task/name; case.mkdir()
                raw=f'(SAIFILE (TIMESCALE 1 ps) (DURATION {cycles*6667}.00) (INSTANCE SharedTest (INSTANCE Cpu (NET (clk (T0 1) (T1 1) (TX 0) (TC 3)) (idle (T0 0) (TX {cycles*6667}) (TC 0))))))'
                (case/'task.saif').write_text(raw); (case/'run.log').write_text('STRICT GUARDS PASSED FIXTURE')
                activity={'status':'PASS_PHYSICAL_TCM_TASK_AND_SYSTEM_ACTIVITY','cycles':cycles,'duration_seconds':cycles*6.667e-9,
                    'saif_sha256':sha(case/'task.saif'),'TX_entries':2,'TX_nonzero_entries':1}
                (case/'Activity.json').write_text(json.dumps(activity)); tasks[name]=activity
                evidence.update({str(p):sha(p) for p in case.iterdir()})
            (task/'SystemActivitySummary.json').write_text(json.dumps({'both_tasks_use_same_repaired_firmware':True,
                'original_ff1_preserved':True,'evidence_sha256':evidence,'tasks':tasks}))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            prepare(task,out,tools)
            self.assertTrue((out/'ff1/RawUnknowns.json').exists())
            self.assertEqual(json.loads((out/'ff1/RawUnknowns.json').read_text())['unknown_signals'],1)
            power='Cell Internal Power = 40 mW\nNet Switching Power = 1000 uW\nTotal Dynamic Power = 41 mW\nCell Leakage Power = 200 uW\n'
            cov='Nets 99(99.00%) 1(1.00%) 0(0.00%) 100\nPorts 10(100.00%) 0(0.00%) 0(0.00%) 10\nPins 99(99.00%) 1(1.00%) 0(0.00%) 100\n'
            for name in tasks:
                case=out/name
                (case/'dc.log').write_text('SYSTEM_POWER_REPORT_COMPLETE: FIXTURE\n')
                (case/'power_view.sdc').write_bytes((review/'clock_ports_corrected.sdc').read_bytes())
                (case/'tool_status.txt').write_text('NETLIST: UNCHANGED\nSAIF_SCOPE: SharedTest/Cpu\nMAPPING_MODE: TEST_FIXTURE\n')
                (case/'power.rpt').write_text(power); (case/'saif_coverage.rpt').write_text(cov)
                (case/'saif_hierarchy.rpt').write_text('Report: saif\n-hierarchy\n'+cov)
                (case/'private_sram_power.rpt').write_text('Totals (56 cells) 3.322mW 4.717uW 3.326mW (100%) 101.690uW\n')
                for filename in ('shared_itcm_power.rpt','shared_dtcm_power.rpt'):
                    (case/filename).write_text('Totals (32 cells) 5mW 0.1mW 5.1mW (100%) 20uW\n')
            finish(out)
            self.assertTrue((out/'SystemPowerReports.partial.tar.gz').exists())
            result=json.loads((out/'SystemPowerSummary.json').read_text())
            self.assertTrue(result['acceptance'].startswith('PENDING_'))
            for path,content in before.items(): self.assertEqual(path.read_bytes(),content)
            (task/'ff1/task.saif').write_text('ALTERED')
            with self.assertRaisesRegex(ValueError,'Frozen input changed'): finish(out)

    def test_explicit_power_units_and_macro_accounting(self):
        result=parse_power('Cell Internal Power = 20 mW\nNet Switching Power = 500 uW\nTotal Dynamic Power = 20.5 mW\nCell Leakage Power = 200 uW\n')
        self.assertAlmostEqual(result['total_w'],.0207)
        text='Totals (56 cells) 3.322mW 4.717uW 3.326mW (100%) 101.690uW\n'
        macros=parse_macro_power(text,56)
        self.assertAlmostEqual(macros['total_w'],.00342769)
        for bad,count in ((text,64),(text.replace('101.690uW','101.690'),56),(text.replace('3.326mW','7mW'),56)):
            with self.assertRaises(ValueError): parse_macro_power(bad,count)

    def test_coverage_keeps_default_activity_counts(self):
        text='Nets 75194(99.85%) 112(0.15%) 0(0.00%) 75306\nPorts 241(100.00%) 0(0.00%) 0(0.00%) 241\nPins 295549(99.58%) 1232(0.42%) 0(0.00%) 296781\n'
        result=coverage(text)
        self.assertEqual(result['pins']['default']['count'],1232)
        with self.assertRaises(ValueError): coverage(text.replace('75306','75305'))

    def test_tcl_rejects_failed_annotation_wrong_macro_inventory_and_power_error(self):
        for mode,expected in (('pass',0),('no_auto',0),('bad_saif',1),('bad_macro',1),('power_error',1),('native_map',0),('bad_map',1),('bad_start',1),('missing_activation',1)):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                interp=tkinter.Tcl(); interp.setvar('Mode',mode)
                for name in ('TPU_SYSTEM_POWER_DDC','TPU_STDCELL_DB','TPU_SRAM_DB','TPU_SYSTEM_DB','TPU_SYSTEM_POWER_SAIF'):
                    interp.setvar('env('+name+')',name)
                interp.setvar('env(TPU_SYSTEM_POWER_CASE)',directory)
                interp.eval('catch {unset ::env(TPU_SYSTEM_NAME_MAP)}')
                if mode in ('native_map','bad_map'):
                    native=Path(directory)/'map.native'; native.write_text('SAIF name mapping file\ndesign e203_cpu_top\n')
                    interp.setvar('env(TPU_SYSTEM_NAME_MAP)',str(native))
                interp.eval(r'''
proc exit {code} {set ::TestExit $code; error TEST_EXIT}
proc read_ddc {args} {
    set ::CheckpointRead 1
    set ::MappingActiveAtRead [info exists ::MapActive]
    return {e203_cpu_top e203_cpu_MASTER1 e203_srams}
}
proc get_designs {args} {return e203_cpu_top}
proc current_design {args} {}
proc link {} {return 1}
proc all_clocks {} {return Clock}
proc sizeof_collection {items} {return [llength $items]}
proc get_clocks {args} {return [lindex $args end]}
proc get_attribute {object attribute} {
    if {$attribute eq "period"} {return 6.666667}
    return [expr {[string match P* $object] ? "RAMSP1024X16" : "RAMSP4096X16"}]
}
proc get_cells {args} {
    set filter [lindex $args end]
    if {[string match *RAMSP1024X16* $filter]} {return [lrepeat [expr {$::Mode eq "bad_macro" ? 55 : 56}] Private]}
    if {[string match *RAMSP4096X16* $filter]} {return [lrepeat 64 Shared]}
    return {Private0 Shared0 Logic0}
}
proc get_object_name {object} {return $object}
proc foreach_in_collection {name items body} {upvar 1 $name item; foreach item $items {uplevel 1 $body}}
proc filter_collection {items filter} {return [lrepeat 32 Shared]}
proc get_ports {name} {return $name}
proc remove_output_delay {args} {}
proc create_generated_clock {args} {}
proc set_clock_uncertainty {args} {}
proc set_clock_transition {args} {}
proc write_sdc {args} {set f [open [lindex $args end] w]; puts $f {FIXTURE SDC}; close $f}
proc help {args} {puts [expr {$::Mode eq "no_auto" ? "read_saif -input -instance_name -verbose" : "read_saif -input -instance_name -map_names -auto_map_names -verbose"}]}
proc redirect {path body} {
    rename puts SavedPuts
    set ::Captured ""
    proc puts {args} {append ::Captured [lindex $args end] "\n"}
    set code [catch {uplevel 1 $body} value options]
    rename puts {}; rename SavedPuts puts
    if {$code} {return -options $options $value}
    set f [open $path w]; puts -nonewline $f "$::Captured$value"; close $f
}
proc reset_switching_activity {args} {set ::ActivityReset 1}
proc saif_map {args} {
    if {[lindex $args 0] eq "-start"} {
        if {[info exists ::CheckpointRead]} {error "Mapping activated after checkpoint import"}
        if {$::Mode eq "bad_start"} {return 0}
        set ::MapActive 1
        return {mapping enabled}
    }
    if {![info exists ::ActivityReset] || [lindex $args 0] ne "-read_map"} {error "wrong native map protocol"}
    if {$::Mode eq "bad_map"} {return 0}
    set ::NativeMapLoaded 1
    return {native mapping loaded}
}
proc read_saif {args} {
    if {![info exists ::ActivityReset]} {error "stale activity"}
    if {("-auto_map_names" in $args || "-map_names" in $args) && (![info exists ::MapActive] || !$::MappingActiveAtRead)} {
        error {The SAIF name mapping mechanism is not active. (PWR-604)}
    }
    if {[lindex $args 3] ne "SharedTest/Cpu"} {error "wrong SAIF scope"}
    if {$::Mode eq "native_map"} {
        if {![info exists ::NativeMapLoaded] || "-map_names" ni $args} {error "native mapping not loaded/used"}
        if {"-auto_map_names" in $args} {error "unexpected mapping mode combination"}
    } elseif {$::Mode ne "no_auto" && "-auto_map_names" ni $args} {error "supported mapping not used"}
    if {$::Mode eq "no_auto" && "-auto_map_names" in $args} {error "unsupported mapping option"}
    if {$::Mode eq "bad_saif"} {return 0}
    return 1
}
proc report_saif {args} {return COVERAGE}
proc report_power {args} {
    if {$::Mode eq "power_error"} {error "power license failure"}
    if {[llength $args] && [llength [lindex $args 2]]!=[lindex $args 4]} {error "incomplete macro reporting"}
    return POWER
}
proc report_units {} {return UNITS}
proc get_switching_activity {args} {return {probability=0.5 toggle_rate=0.3 type=simulated}}
''')
                original=Path.cwd()
                try:
                    script=Path(__file__).with_name('SystemPower.tcl').resolve()
                    if mode=='missing_activation':
                        broken=Path(directory)/'MissingActivation.tcl'
                        broken.write_text(re.sub(r'\s*# BEGIN_SAIF_MAPPING_LIFECYCLE.*?# END_SAIF_MAPPING_LIFECYCLE','',script.read_text(),flags=re.S))
                        script=broken
                    with self.assertRaises(tkinter.TclError): interp.call('source',str(script))
                    self.assertEqual(int(interp.getvar('TestExit')),expected)
                    if expected==0:
                        self.assertTrue((Path(directory)/'private_sram_power.rpt').exists())
                        self.assertIn('NETLIST: UNCHANGED',(Path(directory)/'tool_status.txt').read_text())
                finally:
                    os.chdir(original)
                    interp.eval('catch {unset ::env(TPU_SYSTEM_NAME_MAP)}')


if __name__=='__main__': unittest.main()
