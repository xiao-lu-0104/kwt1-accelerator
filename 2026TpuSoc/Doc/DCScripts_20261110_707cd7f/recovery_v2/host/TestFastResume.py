"""Validate selection equivalence and v2 recovery guards with mock collections/EDA."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import TestResume
from BuildFastResume import files_for_build

HERE = Path(__file__).resolve().parent
TestResume.ENTRY = HERE.parents[1] / 'workspace/Server/tpusoc_hold_recovery_20261110_707cd7f_v2.sh'
# The shared tests use a marker argument for extraction, so accept the v2 marker.
original_extract = TestResume.extract_fixture


def extract(entry, marker, out):
    if entry.name.endswith('_v2.sh'):
        marker = 'FAST_HOLD_RECOVERY_707CD7F'
    return original_extract(entry, marker, out)


TestResume.extract_fixture = extract


@unittest.skipIf(os.name == 'nt', 'Bash tests run in WSL')
class FastResume(TestResume.Resume):
    def test_payload_and_tcl_no_rtl_resynthesis(self):
        expected = files_for_build()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            extract(TestResume.ENTRY, '', out)
            for name, data in expected.items():
                self.assertEqual((out / name).read_bytes(), data)
            tcl = (out / 'tools/Resume.tcl').read_text()
            self.assertNotIn('add_to_collection $Frozen', tcl)
            self.assertIn('set Frozen [FastFrozenCollection]', tcl)
            self.assertIn('HOLD_STAGE: compile_hold_start', tcl)
            self.assertNotIn('if {![compile_ultra', tcl)
            check = subprocess.run(['sha256sum', '--quiet', '-c', 'PACKAGE.sha256'], cwd=out)
            self.assertEqual(check.returncode, 0)

    def test_native_filter_matches_original_predicate_and_rejects_bad_selection(self):
        script = '''
proc InSram {Name} {return [string match {Tpu/Core/Sram/*} $Name]}
proc SramAncestor {Name} {return [expr {$Name in {Tpu Tpu/Core Tpu/Core/Sram}}]}
set ::All {Tpu Tpu/Core Tpu/Core/Sram Tpu/Core/Sram/M0 Tpu/Core/Sram/Register nice_logic Tpu/Core/Matrix/U1 {Tpu/Core/Vector/reg[0]}}
set ::Selected {nice_logic Tpu/Core/Matrix/U1 {Tpu/Core/Vector/reg[0]}}
proc get_cells {args} {return $::All}
proc sizeof_collection {x} {return [llength $x]}
proc get_object_name {x} {return $x}
proc foreach_in_collection {var collection body} {uplevel 1 [list foreach $var $collection $body]}
proc filter_collection {all expr} {
    if {$expr ne {full_name !~ Tpu/Core/Sram/* && full_name != Tpu && full_name != Tpu/Core && full_name != Tpu/Core/Sram}} {error "filter changed"}
    return $::Selected
}
source {''' + str(HERE / 'FastFreeze.tcl') + '''}
if {[FastFrozenCollection] ne $::Selected} {error "selection mismatch"}
set ::Selected {nice_logic Tpu/Core/Matrix/U1}
if {![catch {FastFrozenCollection}]} {error "missing cell accepted"}
set ::Selected {nice_logic Tpu/Core/Matrix/U1 Tpu/Core/Sram/Register}
if {![catch {FastFrozenCollection}]} {error "SRAM cell accepted"}
puts "FAST_FREEZE_MOCK_PROTOCOL_PASS"
'''
        result = subprocess.run(['tclsh'], input=script.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout.decode())
        self.assertIn('FAST_FREEZE_MOCK_PROTOCOL_PASS', result.stdout.decode())

    def test_earlier_recovery_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            out = home / 'soc/tpusoc_hold_recovery_20261110_707cd7f_v2_test'
            out.mkdir(parents=True)
            extract(TestResume.ENTRY, '', out)
            previous = home / 'soc/tpusoc_hold_recovery_20261110_707cd7f_old/mapped'
            previous.mkdir(parents=True)
            (previous / 'candidate.ddc').write_text('TEST_RECENT_CANDIDATE')
            run = subprocess.run(['python3', str(out / 'tools/Resume.py'), str(out)], env=dict(os.environ, HOME=str(home)),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('earlier recovery has a candidate', run.stdout.decode())

    def test_active_recovery_rejected_without_signalling_it(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            out = home / 'soc/tpusoc_hold_recovery_20261110_707cd7f_v2_test'
            out.mkdir(parents=True)
            extract(TestResume.ENTRY, '', out)
            fake = subprocess.Popen(['bash', '-c', 'exec -a "dc_shell /soc/tpusoc_hold_recovery_20261110_707cd7f_old/tools/Resume.tcl" sleep 30'])
            try:
                run = subprocess.run(['python3', str(out / 'tools/Resume.py'), str(out)], env=dict(os.environ, HOME=str(home)),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn('still running; leave it untouched', run.stdout.decode())
                self.assertIsNone(fake.poll())
            finally:
                fake.terminate()
                fake.wait()


if __name__ == '__main__':
    unittest.main()
