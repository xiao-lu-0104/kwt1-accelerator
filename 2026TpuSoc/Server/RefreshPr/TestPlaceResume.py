"""Exercise checkpoint selection and installed-option guards for PLACE-042 recovery."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from MakePlaceResume import runner,stage

HERE=Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    def test_resume_from_saved_pg_not_failed_placement(self):
        module={'__name__':'fixture','__file__':str(HERE/'PlaceResume.py')}
        exec(compile(runner(),'<frozen-place-runner>','exec'),module)
        self.assertEqual(module['PHASES'][0][0],'03_place')
        with tempfile.TemporaryDirectory() as d:
            soc=Path(d);original=soc/'original';p=soc/'tpusoc_full_pr_recovery_20261109_fixture'
            (p/'stages/03_place').mkdir(parents=True);pg=p/'stages/02_pg/system_1109.nlib'
            (p/'RecoveryFailure.json').write_text(json.dumps({'failed_phase':'03_place','last_successful_library':str(pg)}))
            (p/'RecoveryProgress.json').write_text(json.dumps({'stages':[{'phase':'02_pg','complete':True}]}))
            (p/'RecoveryInputs.json').write_text(json.dumps({'source':str(original),'original_files':{},'tools':{},'library_snapshots':{}}))
            (p/'stages/03_place/icc2.log').write_text('Error: No valid scan def found. (PLACE-042)')
            self.assertEqual(module['saved_pg'](soc,original),(p,pg))
            (p/'stages/03_place/icc2.log').write_text('Unrelated failure')
            with self.assertRaises(ValueError):module['saved_pg'](soc,original)
        ast.parse(runner().decode(),feature_version=(3,6))

    @unittest.skipUnless(shutil.which('tclsh'),'Tcl runtime required')
    def test_actual_tcl_requires_installed_no_scan_option(self):
        with tempfile.TemporaryDirectory() as d:
            for supported in (True,False):
                root=Path(d)/str(supported);root.mkdir()
                (root/'FullStage.tcl').write_bytes(stage())
                shutil.copyfile(str(HERE/'../FinalBackend/PrCommon.tcl'),str(root/'PrCommon.tcl'))
                harness=(HERE/'TestFullStage.tcl').read_text()
                start=harness.index('foreach {Source Name}')
                end=harness.index('\ncd $Out',start)
                harness=harness[:start]+harness[end:]
                harness=harness.replace('SYNTAX -ref_libs','SYNTAX -value -ref_libs')
                override='''proc get_app_options args {return {'''+('place.coarse.continue_on_missing_scandef' if supported else '')+'''}}
proc set_app_options args {
    if {$args ne {-name place.coarse.continue_on_missing_scandef -value true}} {error "unexpected setting"}
    set ::NoScan 1
    return 1
}
rename place_opt {}
proc place_opt args {
    if {![info exists ::NoScan]} {error "no-scan setting must precede place_opt"}
    return 1
}
'''
                harness=harness.replace('source [file join $Out FullStage.tcl]',override+'source [file join $Out FullStage.tcl]')
                (root/'Harness.tcl').write_text(harness)
                result=subprocess.run(['tclsh',str(root/'Harness.tcl'),str(root),'03_place'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                self.assertEqual(result.returncode,0 if supported else 2,result.stdout.decode())
                self.assertEqual((root/'checkpoint.def').exists(),supported)


if __name__=='__main__':unittest.main()
