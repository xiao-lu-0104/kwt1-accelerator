"""Report parsing, no-regression selection, and actual continuation Tcl protocol."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from BuildContinuePr import build_files
from BuildPr import HERE


def module(root):
    files=build_files()
    for n,b in files.items():
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    sys.path.insert(0,str(root/'tools'))
    spec=importlib.util.spec_from_file_location('ContinuationFixture',str(root/'tools/ContinuePr.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def conn(cells=0,wires=0):
    return '\n'.join('Verify net '+n+' connectivity\nNumber of floating wires: '+str(wires)+
        '\nNumber of floating vias: 0\nNumber of floating std cells: '+str(cells)+
        '\nNumber of floating hard macros: 0\nNumber of floating terminals: 0' for n in ('VDD','VSS'))


class Tests(unittest.TestCase):
    def test_whole_flow_falls_back_then_routes_without_repeating_dc(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);m=module(root);home=root/'home';soc=home/'soc';soc.mkdir(parents=True)
            source=soc/'initial_fixture';(source/'inputs').mkdir(parents=True)
            (source/'design').mkdir();(source/'design/PortTerminalGeometry.tsv').write_text('fixture')
            (source/'inputs/candidate.v').write_text('new707netlist')
            (source/'inputs/candidate.sdc').write_text('new707constraints')
            refs={}
            for label in ('rvt','private','shared'):
                ref=source/('library_'+label)/(label+'.ndm');ref.mkdir(parents=True)
                (ref/'db').write_text(label);refs[str(ref)]=m.tree(ref)
            inputs={'inputs':{},'source_commit':m.REV,'design_sdc_sha256':m.sha(source/'inputs/candidate.sdc'),
                    'reference_snapshots':refs,'expected_serialized_period_ns':'6.66667'}
            summary={'design_netlist_sha256':m.sha(source/'inputs/candidate.v')}
            (source/'NewPrInputs.json').write_text(json.dumps(inputs));(source/'NewPrSummary.json').write_text(json.dumps(summary))
            ext=soc/'tpusoc_pg_v6_707cd7f_fixture';(ext/'design/system_707cd7f.nlib').mkdir(parents=True)
            (ext/'design/system_707cd7f.nlib/db').write_text('saved_v6')
            (ext/'conn_v6.rpt').write_text(conn(6,10));(ext/'pg_drc_v6.txt').write_text('original detail')
            prepare=soc/'tpusoc_pr_prepare_20261109_fixture';prepare.mkdir()
            (prepare/'RcInventory.json').write_text('{}')
            (prepare/'BackendPrepareSummary.json').write_text(json.dumps({'result':'NEW_1109_BACKEND_PREPARATION_COMPLETE'}))
            phy=soc/'tpusoc_icc2_start_20261108_mTq1LE';phy.mkdir()
            (phy/'PrInputs.json').write_text(json.dumps({'icc2':'fixture_icc2','icc2_flag':'-file'}))
            rc={}
            for key in ('tlup','map'):
                p=root/key;p.write_text('reference_'+key);rc[key]=str(p)
            out=root/'output';out.mkdir();(out/'Config.json').write_text(json.dumps({'initial_package_sha256':'fixture'}))
            actions=[]
            def fake_native(args):
                cwd=Path(args[args.index('--cwd')+1]);log=Path(args[args.index('--log')+1])
                action=__import__('re').search(r'set Action \{([^}]+)\}',(cwd/'ContinueConfig.tcl').read_text()).group(1)
                actions.append(action)
                if action=='connectivity':(cwd/'connectivity.rpt').write_text(conn(6,10))
                elif action=='drc':(cwd/'drc.rpt').write_text('Total number of errors found: 28006\n27230 insufficient spacings on V1\n776 insufficient spacings on M4\n')
                else:
                    (cwd/'checkpoint.def').write_text('NETS 150 ;\n'+''.join('- n%d + ROUTED M3 ( 0 0 ) ;\n'%i for i in range(150))+'END NETS\n')
                    for n in ('routed.v','routed.sdc','setup.rpt','hold.rpt','route_check.rpt'):(cwd/n).write_text('fixture report')
                log.write_text(('CONTINUE_CORE_SAVED: '+action+'\n' if action not in ('connectivity','drc') else '')+'CONTINUE_PHASE_COMPLETE: '+action+'\n')
                return 0
            with patch.object(m.Path,'home',return_value=home),patch.object(m,'choose_source',return_value=(source,summary)),\
                 patch.object(m,'select_rails',return_value={'audit':str(root/'audit'),'files':{}}),\
                 patch.object(m,'select_rc',return_value=rc),patch.object(m.subprocess,'call',side_effect=fake_native):
                m.main(out)
            result=json.loads((out/'ContinueSummary.json').read_text())
            self.assertTrue(json.loads((out/'PgDecision.json').read_text())['fallback_used'])
            self.assertEqual(result['ordinary_net_route_records'],150)
            self.assertTrue(result['original_inputs_unchanged'])
            self.assertFalse(result['pg_final']['connectivity']['clean'])
            self.assertEqual(actions.count('03_place'),1);self.assertEqual(actions.count('04_cts'),1)
            self.assertTrue((out/'OpenRoutedLayout.tcl').is_file())
            self.assertTrue((out/'ContinueReports.tar.gz').is_file())
            self.assertFalse((source/'design/system_707cd7f.nlib').exists())

    def test_native_summary_parsing_and_unknown_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            m=module(Path(d))
            c=m.parse_connectivity(conn(6,10));self.assertTrue(c['known']);self.assertFalse(c['clean'])
            self.assertFalse(m.parse_connectivity('command returned0')['known'])
            raw='Total number of errors found: 28006\n27230 insufficient spacings on V1\n776 insufficient spacings on M4\n'
            drc=m.parse_drc(raw);self.assertEqual(drc['total'],28006);self.assertEqual(drc['shorts'],0)
            self.assertFalse(m.parse_drc(raw.replace('28006','28007'))['known'])
            self.assertFalse(m.parse_drc('Total number of errors found: 0\nError: check failed')['clean'])

    def test_candidate_cannot_exchange_new_drc_for_connectivity(self):
        with tempfile.TemporaryDirectory() as d:
            m=module(Path(d))
            def item(cells,errors):
                return {'connectivity':m.parse_connectivity(conn(cells,10)),
                        'drc':m.parse_drc('Total number of errors found: '+str(errors)+'\n'+str(errors)+' insufficient spacings on V1\n')}
            base=item(6,28006)
            self.assertTrue(m.improves(item(0,776),base))
            self.assertFalse(m.improves(item(0,28007),base))
            self.assertFalse(m.improves(item(6,28006),base))
            unknown=item(0,776);unknown['connectivity']['known']=False
            self.assertFalse(m.improves(unknown,base))

    def test_external_source_unique_and_no_old_design_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);m=module(root)
            with self.assertRaises(ValueError):m.external(root,'v6')
            p=root/'tpusoc_pg_v6_707cd7f_fixture';(p/'design/system_707cd7f.nlib').mkdir(parents=True)
            (p/'conn_v6.rpt').write_text(conn());(p/'pg_drc_v6.txt').write_text('fixture')
            self.assertEqual(m.external(root,'v6')[0],p)
            self.assertIsNone(m.external(root,'v7',required=False))

    def test_python36_all_deployed_modules(self):
        for name,data in build_files().items():
            if name.endswith('.py'):ast.parse(data.decode(),filename=name,feature_version=(3,6))

    def test_actual_tcl_actions_and_failed_core(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);module(root);tools=root/'tools'
            prefix=(HERE/'TestPgStage.tcl').read_text().split('if {$Kind in {connectivity drc}}',1)[0]
            suffix=r'''
rename get_attribute RawAttr
proc get_attribute {Object A} {
    set C [lindex [split $Object /] 0]
    switch $A {
        origin {return [lindex [RawAttr $C bbox] 0]}
        orientation {return R0}
        is_fixed {return true}
        object_class {return cell}
        bbox {return [RawAttr $C bbox]}
        default {return [RawAttr $Object $A]}
    }
}
proc get_pins args {
    if {[lsearch -exact $args -of_objects]<0} {return PG_PIN}
    set C [lindex $args end];return [list $C/VDDCE $C/VDDPE $C/VSSE]
}
proc get_corners args {return INITIAL}
proc all_clocks {} {return {CoreClock CoreCsrClock InspectCoreClock}}
proc get_app_options args {return [lindex $args end]}
proc set_app_options args {return 1}
foreach N {read_parasitic_tech set_parasitic_parameters set_ignored_layers set_propagated_clock} {proc $N args {return 1}}
proc create_pg_vias args {
    if {[lsearch -exact $args -allow_parallel_objects]<0} {error "Missing parallel rail guard"}
    return 1
}
proc write_def Name {
    set F [open $Name w];puts $F {NETS 150 ;}
    for {set I 0} {$I<150} {incr I} {puts $F "- n$I + ROUTED M3 ( 0 0 ) ;"}
    puts $F {END NETS};close $F;return 1
}
proc write_verilog Name {set F [open $Name w];puts $F {module e203_cpu_top; endmodule};close $F;return 1}
proc write_sdc args {set F [open [lindex $args end] w];puts $F {create_clock -period 6.66667};close $F;return 1}
proc report_parasitic_parameters {} {puts {INITIAL early=TYP707CONT late=TYP707CONT}}
foreach N {place_opt clock_opt route_auto route_opt} {proc $N args {if {$::Bad eq "core_fail"} {return 0};return 1}}
foreach N {report_timing report_qor report_constraints check_routes report_clock_qor check_legality} {
    proc $N args {if {![file exists checkpoint.def]} {error "Report before saved checkpoint"};puts "Fixture report";return 1}
}
proc man args {puts {SYNTAX -name -value -output -ref_libs -max_cores -layers -nets -from_layers -to_layers -via_masters -within_bbox -allow_parallel_objects -via_array_dimension -tlup -layermap -sanity_check -corners -early_spec -late_spec -early_temperature -late_temperature -check_macro_pins -check_std_cell_pins}}
proc check_pg_connectivity args {
    foreach Net {VDD VSS} {
        puts "Verify net $Net connectivity"
        foreach {Label Value} {wires 10 vias 0 {std cells} 6 {hard macros} 0 terminals 0} {puts "Number of floating $Label: $Value"}
    }
    return {c0}
}
proc check_pg_drc args {
    set F [open pg_drc_details.txt w];puts $F "Error type: insufficient spacing\nLayer: M4";close $F
    puts "Total number of errors found: 1\n1 insufficient spacings on M4";return 1
}
source [file join $Tools IoGeometry.tcl]
source [file join $Tools PgPhysical.tcl]
set Leaves [dict create]
foreach C $Cells {dict set Leaves $C [dict get $Refs $C]}
PgWriteSignature BaselineLeaves.tsv $Leaves
PgWriteSignature BaselineMacros.tsv [PgMacroSignature]
set F [open BaselineIo.tsv w];puts $F "port\tterminal\tx1\ty1\tx2\ty2\tlayers"
foreach P {clk rst_n} {puts $F "$P\tT:$P\t0\t100\t0.07\t100.07\tM3"};close $F
set F [open ContinueConfig.tcl w]
puts $F "set Action {$Kind}\nset DesignLib {[file join $Out current.nlib]}\nset RefLibs {a.ndm b.ndm c.ndm}\nset ExpectedPeriod 6.66667"
puts $F {set BaselineLeaves BaselineLeaves.tsv
set BaselineMacros BaselineMacros.tsv
set BaselineIo BaselineIo.tsv
set RcTlu fixture.tluplus
set RcMap fixture.map}
close $F
if {$Bad eq "bad_leaf"} {dict set Refs c0 WRONG}
source [file join $Tools ContinuePr.tcl]
'''
            harness=root/'Harness.tcl';harness.write_text(prefix+suffix)
            for action in ('audit','repair','connectivity','drc','01_rc','03_place','04_cts','05_route','06_route_opt','07_export'):
                out=root/action
                r=subprocess.run(['tclsh',str(harness),str(tools),str(out),action,''],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,action+'\n'+r.stdout+r.stderr)
                self.assertIn('CONTINUE_PHASE_COMPLETE: '+action,r.stdout)
                if action not in ('connectivity','drc'):self.assertTrue((out/'checkpoint.def').is_file())
            for action,bad in [('03_place','core_fail'),('audit','bad_leaf')]:
                out=root/(action+bad)
                r=subprocess.run(['tclsh',str(harness),str(tools),str(out),action,bad],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertFalse((out/'checkpoint.def').exists())


if __name__=='__main__':unittest.main()
