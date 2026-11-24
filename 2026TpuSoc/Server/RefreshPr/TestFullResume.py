"""Regression checks for the observed PG timeout and installed enum mismatch."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from MakeFullResume import patched_stage
from ResumeFull import find_source

HERE=Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    def test_saved_before_reports_and_drc_isolated(self):
        stage=patched_stage().decode()
        self.assertLess(stage.index('PrStep save_stage_block'),stage.index('qor.rpt {report_qor}'))
        self.assertIn('FULL_PR_CORE_SAVED:',stage)
        self.assertNotIn('pg_drc.rpt {check_pg_drc}',stage)
        self.assertNotIn('pg_connectivity.rpt {',stage)
        check=(HERE/'PgCheck.tcl').read_text()
        self.assertIn('-check_std_cell_pins all',check)
        self.assertNotIn('-check_std_cell_pins true',check)

    def test_source_requires_actual_timeout_and_rc_completion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p=root/'tpusoc_full_pr_20261109_fixture';p.mkdir()
            (p/'runner.log').write_text('PHASE_COMPLETE: 01_rc\nSTAGE_TIMEOUT: 02_pg\n')
            (p/'FullPrFailure.json').write_text(json.dumps({'failed_phase':'02_pg'}))
            self.assertEqual(find_source(root),p)
            q=root/'tpusoc_full_pr_20261109_another';shutil.copytree(str(p),str(q))
            with self.assertRaises(ValueError):find_source(root)
            shutil.rmtree(str(q));(p/'runner.log').write_text('STAGE_RUNNING: 02_pg')
            with self.assertRaises(ValueError):find_source(root)

    @unittest.skipUnless(shutil.which('tclsh'),'Tcl runtime required')
    def test_recovered_tcl_saves_before_any_check_and_enum_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            fixture=Path(d)
            (fixture/'FullStage.tcl').write_bytes(patched_stage())
            shutil.copyfile(str(HERE/'../FinalBackend/PrCommon.tcl'),str(fixture/'PrCommon.tcl'))
            harness=(HERE/'TestFullStage.tcl').read_text()
            # Replace only fixture source locations; use the real recovered Tcl stage.
            start=harness.index('foreach {Source Name}')
            end=harness.index('\ncd $Out',start)
            harness=harness[:start]+harness[end:]
            harness=harness.replace('source [file join $Out FullStage.tcl]',
                'rename check_pg_drc {}\nproc check_pg_drc args {error "DRC must be isolated"}\n'+
                'rename check_pg_connectivity {}\nproc check_pg_connectivity args {error "connectivity must be isolated"}\n'+
                'rename report_qor {}\nproc report_qor {} {if {![file exists checkpoint.def]} {exit 77};puts "saved-before-reports"}\n'+
                'source [file join $Out FullStage.tcl]')
            (fixture/'Harness.tcl').write_text(harness)
            result=subprocess.run(['tclsh',str(fixture/'Harness.tcl'),str(fixture),'02_pg'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode,0,result.stdout.decode())
            self.assertIn(b'FULL_PR_CORE_SAVED: 02_pg',result.stdout)
            # Execute the actual isolated check Tcl with a strict enum mock.
            (fixture/'FullConfig.tcl').write_text('set DesignLib x\nset RefLibs {}\nset CheckKind pg_connectivity\n')
            isolated='''proc open_lib args {return 1}
proc set_ref_libs args {return 1}
proc open_block args {return 1}
proc link_block args {return 1}
proc man args {puts {SYNTAX -check_macro_pins -check_std_cell_pins}}
proc redirect {name body} {uplevel 1 $body}
proc check_pg_connectivity args {
    set i [lsearch -exact $args -check_std_cell_pins]
    if {[lindex $args [expr {$i+1}]] ne "all"} {error {invalid enum}}
    puts {fixture connectivity report}
}
source {'''+str(HERE/'PgCheck.tcl').replace('\\','/')+'''}
'''
            (fixture/'Isolated.tcl').write_text(isolated)
            # PgCheck sources PrCommon relative to its own deployed location.
            shutil.copyfile(str(HERE/'PgCheck.tcl'),str(fixture/'PgCheck.tcl'))
            isolated=isolated.replace(str(HERE/'PgCheck.tcl').replace('\\','/'),str(fixture/'PgCheck.tcl').replace('\\','/'))
            (fixture/'Isolated.tcl').write_text(isolated)
            result=subprocess.run(['tclsh',str(fixture/'Isolated.tcl')],cwd=str(fixture),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode,0,result.stdout.decode())
            self.assertIn(b'PG_CHECK_EXECUTED: pg_connectivity',result.stdout)


if __name__=='__main__':unittest.main()
