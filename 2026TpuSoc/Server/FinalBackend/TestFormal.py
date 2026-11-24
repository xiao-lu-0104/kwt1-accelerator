"""Formal orchestration checks; these mocks are not an equivalence proof."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from Formal import classify, clean_manual, manual_section, read_status, script_flag, tcl_list, validated_sources, review_array_warning, failure_summary, diagnostic_files, validated_guidance, NETLIST_SHA, BUNDLE_SHA, RTL, TOP
from Preflight import sha

HERE = Path(__file__).resolve().parent
MOCK_TCL = '''
set VerifyCalled 0
set DiagnosticReturn 1
set DiagnosticManualOptions {-verilog -failing -summary}
set hdlin_unresolved_modules black_box
set synopsys_auto_setup false
set GuidanceLoaded 0
proc set_svf {name} {
    if {[info exists ::ReadCommands] || [info exists ::LibraryRead]} {error "SVF must precede design/library reads"}
    if {$::synopsys_auto_setup ne "false"} {error "Automatic setup policies must remain disabled"}
    set ::GuidanceLoaded 1
    return $::GuidanceReturn
}
proc exit {code} {return -code error "MOCK_EXIT_$code"}
proc read_db {args} {
    if {!$::GuidanceLoaded} {error "Missing synthesis guidance"}
    set ::LibraryRead 1
    return $::ReadDbReturn
}
proc read_verilog {args} {
    if {[lsearch -exact $args -r] >= 0} {error "package parsed as plain Verilog"}
    lappend ::ReadCommands $args; return 1
}
proc read_sverilog {args} {
    if {[lsearch -exact $args -r] < 0} {error "Reference container required"}
    set index [lsearch -exact $args -define]
    if {$index < 0 || [lindex $args [expr {$index+1}]] ne {SYNTHESIS TPU_SRAM_MODEL}} {
        error "Original synthesis defines must be passed to native SV reader"
    }
    lappend ::ReadCommands $args
    return $::ReadSvReturn
}
proc man {name} {return 1}
proc set_mismatch_message_filter {args} {
    if {$args ne {-warn FMR_ELAB-147}} {error "Only the reviewed message may be acknowledged"}
    set ::WarningAcknowledged 1
}
proc set_top {name} {
    if {[string match r:* $name] && ![info exists ::WarningAcknowledged]} {
        error "Unacknowledged array interpretation risk blocks reference linking"
    }
    lappend ::TopCommands $name; return 1
}
proc match {} {return $::MatchReturn}
proc verify {} {set ::VerifyCalled 1; return $::VerifyReturn}
proc save_session {name} {
    if {!$::VerifyCalled || $::VerifyReturn ne "0"} {error "Only diagnose failed verify"}
    set f [open "${name}.fss" w]; puts $f MOCK_SESSION; close $f
    return $::DiagnosticReturn
}
proc write_failing_patterns {args} {
    if {![file exists FailureSession.fss]} {error "Save session before patterns"}
    set f [open "[lindex $args end].v" w]; puts $f MOCK_PATTERN; close $f
    return $::DiagnosticReturn
}
proc analyze_points {args} {
    if {![file exists FailureEvidence/failing.v]} {error "Save patterns before analysis"}
    return $::DiagnosticReturn
}
proc report_analysis_results {args} {return $::DiagnosticReturn}
proc report_guidance {args} {return $::DiagnosticReturn}
proc redirect {file command} {
    set value [uplevel 1 $command]
    set f [open $file w]
    if {[lindex $command 0] eq "man"} {
        puts $f "SYNTAX read_sverilog -r -libname -define $::DiagnosticManualOptions"
    } else {puts $f "MOCK_NATIVE_REPORT $command"}
    close $f
    return $value
}
foreach name {report_black_boxes report_setup_status report_matched_points report_unmatched_points report_failing_points report_aborted_points report_unverified_points} {
    proc $name {args} {return 1}
}
'''


class FormalTests(unittest.TestCase):
    def test_native_manual_and_cli_options_must_be_confirmed(self):
        self.assertEqual(script_flag('Usage fm_shell [-file script]'), '-file')
        self.assertEqual(script_flag('Usage fm_shell [-f script]'), '-f')
        with self.assertRaises(ValueError):
            script_flag('-file_extra flag')
        text = 'FORMAL_COMMAND_MANUAL: read_db\nSYNTAX read_db -technology_library\nFORMAL_COMMAND_MANUAL: set_top\nSYNTAX set_top\n'
        self.assertIn('-technology_library', manual_section(text, 'read_db'))
        with self.assertRaises(ValueError):
            manual_section(text, 'missing')
        self.assertEqual(clean_manual('S\bSY\bYN\bNT\bTA\bAX\bX'), 'SYNTAX')

    def test_paths_are_tcl_data_and_cannot_inject_commands(self):
        self.assertEqual(tcl_list(['/some path/x.sv', '/x/$value[0].sv']), '[list {/some path/x.sv} {/x/$value[0].sv}]')
        for bad in ('x}]; exit', 'x\nset x 1', 'x\\'):
            with self.assertRaises(ValueError):
                tcl_list([bad])

    def test_exit_zero_alone_and_missing_or_false_verify_cannot_be_success(self):
        good = {'RESULT': ['TOOL_VERIFY_TRUE_REVIEW_PENDING'], 'VERIFY_RETURN': ['1']}
        self.assertEqual(classify(good, {'exit_code': 0, 'status': 'EXIT_0'}), 'TOOL_VERIFY_TRUE_REVIEW_PENDING')
        conditional = dict(good, RESULT=['TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING'])
        self.assertEqual(classify(conditional, {'exit_code': 0, 'status': 'EXIT_0'}),
                         'TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING')
        for status in ({}, {'RESULT': ['TOOL_VERIFY_TRUE_REVIEW_PENDING']},
                       {'RESULT': ['TOOL_VERIFY_TRUE_REVIEW_PENDING'], 'VERIFY_RETURN': ['0']}):
            self.assertEqual(classify(status, {'exit_code': 0, 'status': 'EXIT_0'}), 'FORMAL_ATTEMPT_FAILED_OR_INCONCLUSIVE')
        self.assertEqual(classify(good, {'exit_code': 124, 'status': 'TIMEOUT'}), 'FORMAL_TIMEOUT_INCONCLUSIVE')

    def test_reference_sources_are_bound_to_original_synthesis_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['Rtl/' + name + '.sv' for name in RTL]
            names += ['Backend/' + TOP + '.sv', 'Server/Backend/SpFoundry.sv']
            for name in names:
                path = root / 'Project' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('// source fixture ' + name, encoding='utf-8')
            manifest = root / 'Original.sha256'
            manifest.write_text(''.join(sha(root / 'Project' / name) + '  ' + name + '\n' for name in names), encoding='utf-8')
            with patch('Formal.BUNDLE_SHA', sha(manifest)):
                self.assertEqual(len(validated_sources(root, manifest)), 16)
                (root / 'Project/Rtl/TpuDma.sv').write_text('// different RTL', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'differs from original synthesis'):
                    validated_sources(root, manifest)

    def run_tcl(self, match='1', verify='1', read_db='1', read_sv='1', diagnostics='1', manual_options='-verilog -failing -summary', guidance='1'):
        if shutil.which('tclsh'):
            return self.run_external_tcl(match, verify, read_db, read_sv, diagnostics, manual_options, guidance)
        try:
            import tkinter
        except ImportError:
            self.skipTest('Tcl interpreter unavailable; orchestration-only tests still run')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'Guidance.svf').write_text('mock SVF; orchestration only', encoding='utf-8')
            (out / 'FormalConfig.tcl').write_text('set FormalTop e203_subsys_nice_core\n'
                'set FormalSources [list {/reference/source.sv}]\n'
                'set FormalNetlist {/mapped/candidate.v}\nset FormalLibraries [list {/library.db}]\n'
                'set FormalReviewedArrayWarning {FMR_ELAB-147}\nset FormalSvf Guidance.svf\n', encoding='utf-8')
            interpreter = tkinter.Tcl()
            cwd = os.getcwd()
            interpreter.call('cd', out.as_posix())
            try:
                interpreter.eval(MOCK_TCL)
                for name, value in (('MatchReturn', match), ('VerifyReturn', verify), ('ReadDbReturn', read_db),
                                    ('ReadSvReturn', read_sv), ('DiagnosticReturn', diagnostics),
                                    ('DiagnosticManualOptions', manual_options), ('GuidanceReturn', guidance)):
                    interpreter.call('set', name, value)
                with self.assertRaises(tkinter.TclError) as result:
                    interpreter.call('source', (HERE / 'Formal.tcl').as_posix())
                return (str(result.exception), read_status(out / 'FormalStatus.tsv'),
                        interpreter.call('set', 'VerifyCalled'), interpreter.call('set', 'hdlin_unresolved_modules'))
            finally:
                interpreter.call('cd', Path(cwd).as_posix())

    def run_external_tcl(self, match, verify, read_db, read_sv, diagnostics, manual_options, guidance):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'Guidance.svf').write_text('mock SVF; orchestration only', encoding='utf-8')
            (out / 'FormalConfig.tcl').write_text('set FormalTop e203_subsys_nice_core\n'
                'set FormalSources [list {/reference/source.sv}]\n'
                'set FormalNetlist {/mapped/candidate.v}\nset FormalLibraries [list {/library.db}]\n'
                'set FormalReviewedArrayWarning {FMR_ELAB-147}\nset FormalSvf Guidance.svf\n', encoding='utf-8')
            driver = out / 'Driver.tcl'
            driver.write_text(MOCK_TCL + '\nset MatchReturn ' + tcl_list([match]) +
                '\nset VerifyReturn ' + tcl_list([verify]) + '\nset ReadDbReturn ' + tcl_list([read_db]) +
                '\nset ReadSvReturn ' + tcl_list([read_sv]) +
                '\nset DiagnosticReturn ' + tcl_list([diagnostics]) +
                '\nset GuidanceReturn ' + tcl_list([guidance]) +
                '\nset DiagnosticManualOptions ' + tcl_list([manual_options]) + '''
catch {source [lindex $argv 0]} why
set f [open MockReturn.tsv w]
puts $f "EXIT\t$why"
puts $f "CALLED\t$VerifyCalled"
puts $f "POLICY\t$hdlin_unresolved_modules"
close $f
''', encoding='utf-8')
            process = subprocess.run([shutil.which('tclsh'), str(driver), str(HERE / 'Formal.tcl')], cwd=out,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            self.assertEqual(process.returncode, 0, process.stdout.decode(errors='replace'))
            outcome = read_status(out / 'MockReturn.tsv')
            return outcome['EXIT'][0], read_status(out / 'FormalStatus.tsv'), outcome['CALLED'][0], outcome['POLICY'][0]

    def test_tcl_actual_verify_return_is_required_and_unresolved_modules_are_rejected(self):
        code, status, called, policy = self.run_tcl()
        self.assertEqual(code, 'MOCK_EXIT_0')
        self.assertEqual(status['VERIFY_RETURN'], ['1'])
        self.assertEqual(status['REFERENCE_READER'], ['read_sverilog'])
        self.assertEqual(status['REFERENCE_LANGUAGE'], ['SYSTEMVERILOG'])
        self.assertEqual(status['RESULT'], ['TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING'])
        self.assertEqual(status['ARRAY_INDEX_SAFETY'], ['NOT_PROVED'])
        self.assertEqual(status['INTERPRETATION_WARNING'], ['FMR_ELAB-147'])
        self.assertEqual(status['GUIDANCE_READ_RETURN'], ['1'])
        self.assertEqual(status['AUTO_SETUP'], ['DISABLED_GUIDANCE_ONLY'])
        self.assertEqual(int(called), 1)
        self.assertEqual(policy, 'error')

    def test_tcl_failed_match_false_verify_and_library_failure_are_not_passes(self):
        for match, verify, library, called in (('0', '1', '1', 0), ('1', '0', '1', 1),
                                               ('1', '1', '0', 0), ('unexpected', '1', '1', 0)):
            with self.subTest(match=match, verify=verify, library=library):
                code, status, actual, _ = self.run_tcl(match, verify, library)
                self.assertEqual(code, 'MOCK_EXIT_2')
                self.assertEqual(status['RESULT'], ['ATTEMPT_FAILED_OR_INCONCLUSIVE'])
                self.assertEqual(int(actual), called)

    def test_native_sv_read_failure_prevents_match_and_verify(self):
        code, status, called, _ = self.run_tcl(read_sv='0')
        self.assertEqual(code, 'MOCK_EXIT_2')
        self.assertEqual(status['STAGE'][-1], 'read_reference')
        self.assertNotIn('MATCH_RETURN', status)
        self.assertEqual(int(called), 0)

    def test_native_failure_is_retained_after_diagnostics_or_diagnostic_errors(self):
        code, status, _, _ = self.run_tcl(verify='0')
        self.assertEqual(code, 'MOCK_EXIT_2')
        self.assertEqual(status['VERIFY_RETURN'], ['0'])
        self.assertEqual(status['RESULT'], ['ATTEMPT_FAILED_OR_INCONCLUSIVE'])
        self.assertEqual(status['DIAGNOSTIC_START'], ['report_guidance', 'save_session', 'write_failing_patterns', 'analyze_points', 'report_analysis_results'])
        self.assertEqual(len(status['DIAGNOSTIC_COMPLETE']), 5)
        code, status, _, _ = self.run_tcl(verify='0', diagnostics='0')
        self.assertEqual(code, 'MOCK_EXIT_2')
        self.assertEqual(len(status['DIAGNOSTIC_ERROR']), 5)
        self.assertEqual(status['VERIFY_RETURN'], ['0'])
        code, status, _, _ = self.run_tcl(verify='0', manual_options='')
        self.assertEqual(code, 'MOCK_EXIT_2')
        self.assertEqual(status['DIAGNOSTIC_START'], ['save_session'])
        self.assertEqual(len(status['DIAGNOSTIC_ERROR']), 4)
        for match, verify in (('0', '1'), ('1', '1')):
            _, status, _, _ = self.run_tcl(match=match, verify=verify)
            self.assertEqual(status.get('DIAGNOSTIC_START', []), ['report_guidance'] if match == '1' else [])

    def test_svf_failure_or_nonboolean_result_stops_before_design_read_and_verify(self):
        for value in ('0', 'unexpected'):
            code, status, called, _ = self.run_tcl(guidance=value)
            self.assertEqual(code, 'MOCK_EXIT_2')
            self.assertEqual(status['STAGE'][-1], 'read_guidance')
            self.assertEqual(int(called), 0)
            self.assertNotIn('MATCH_RETURN', status)

    def test_guidance_must_match_original_sources_netlist_libraries_and_be_unambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, out = root / 'original', root / 'out'
            (original / 'source').mkdir(parents=True)
            (original / 'mapped').mkdir()
            out.mkdir()
            sources = []
            for name in ('TpuPkg.sv', 'TpuMatmul.sv'):
                path = root / name
                path.write_text('// frozen reference ' + name, encoding='utf-8')
                sources.append(path)
                (original / 'source' / name).write_bytes(path.read_bytes())
            evidence = {'top': TOP, 'bundle_manifest_sha256': BUNDLE_SHA,
                        'source_sha256': {p.name: sha(p) for p in sources}}
            record = original / 'source/Evidence.json'
            record.write_text(json.dumps(evidence), encoding='utf-8')
            netlist = original / 'mapped/candidate.v'
            netlist.write_text('// frozen netlist fixture', encoding='utf-8')
            library = root / 'std.db'
            library.write_bytes(b'library fixture')
            ledger = original / 'library_sha256.txt'
            ledger.write_text(sha(library) + '  ' + str(library) + '\n', encoding='utf-8')
            svf = original / 'default.svf'
            svf.write_bytes(b'original synthesis guidance fixture')
            # A similarly named system SVF must never be selected.
            (root / 'default.svf').write_bytes(b'unrelated system guidance')
            with patch('Formal.NETLIST_SHA', sha(netlist)):
                result = validated_guidance(original, sources, [library], out)
                self.assertEqual(result['original_svf'], str(svf))
                self.assertEqual(sha(Path(result['snapshot'])), sha(svf))
                self.assertEqual(result['native_guidance_acceptance'], 'NOT_YET_CHECKED')
                Path(result['snapshot']).unlink()
                (original / 'mapped/extra.svf').write_bytes(b'other guidance')
                with self.assertRaisesRegex(ValueError, 'unambiguous'):
                    validated_guidance(original, sources, [library], out)
                (original / 'mapped/extra.svf').unlink()
                evidence['top'] = 'e203_cpu_top'
                record.write_text(json.dumps(evidence), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'source evidence'):
                    validated_guidance(original, sources, [library], out)
                evidence['top'] = TOP
                record.write_text(json.dumps(evidence), encoding='utf-8')
                library.write_bytes(b'changed library')
                with self.assertRaisesRegex(ValueError, 'libraries differ'):
                    validated_guidance(original, sources, [library], out)
                library.write_bytes(b'library fixture')
                (original / 'source/TpuMatmul.sv').write_text('// changed', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    validated_guidance(original, sources, [library], out)
            with self.assertRaisesRegex(ValueError, 'netlist differs'):
                validated_guidance(original, sources, [library], out)

    def test_failure_reports_and_counterexamples_are_preserved_without_inferring_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'report_failing_points.rpt').write_text('20 Failing compare points (20 matched, 0 unmatched):\n'
                'Ref DFF r:/WORK/Tpu/Core/Matrix/Column_reg[0]\nImpl DFF i:/WORK/Tpu/Core/Matrix/Column_reg[0]\n', encoding='utf-8')
            (out / 'report_aborted_points.rpt').write_text('No aborted compare points.', encoding='utf-8')
            result = failure_summary(out)
            self.assertEqual(result['listed_failing_count'], 20)
            self.assertEqual(result['listed_reference_points'], ['r:/WORK/Tpu/Core/Matrix/Column_reg[0]'])
            self.assertTrue(result['report_says_no_aborted_points'])
            (out / 'FailureEvidence').mkdir()
            pattern = out / 'FailureEvidence/failing.v'
            pattern.write_text('// native counterexample fixture', encoding='utf-8')
            session = out / 'FailureSession.fss'
            session.write_text('session fixture', encoding='utf-8')
            files, evidence = diagnostic_files(out)
            self.assertEqual(files, [pattern])
            self.assertEqual(evidence['patterns']['FailureEvidence/failing.v']['sha256'], sha(pattern))
            self.assertEqual(evidence['sessions_server_only'][0]['path'], str(session))
            self.assertNotIn(session, files)
            with pattern.open('wb') as stream:
                stream.truncate(64 * 1024 * 1024 + 1)
            files, evidence = diagnostic_files(out)
            self.assertEqual(files, [])
            self.assertEqual(evidence['pattern_archive_status'], 'OVER_64MIB_SERVER_ONLY')

    def test_array_acknowledgement_requires_exact_prior_source_and_warning_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'candidate'
            previous = Path(directory) / 'previous'
            previous.mkdir()
            (root / 'Project/Rtl').mkdir(parents=True)
            for name in ('TpuSram.sv', 'TpuPkg.sv'):
                (root / 'Project/Rtl' / name).write_bytes((HERE.parents[1] / 'Rtl' / name).read_bytes())
            (root / 'MANIFEST.sha256').write_text('candidate fixture', encoding='utf-8')
            source = root / 'Project/Rtl/TpuSram.sv'
            package = root / 'Project/Rtl/TpuPkg.sv'
            log = previous / 'fm_actual.log'
            message = 'Warning: Index may take values outside array bound, may cause simulation mismatch .. '
            text = ''.join(message + '(Signal: RegionData Block: /TpuSram File: ' + str(source) +
                           ' Line: ' + str(line) + ') (FMR_ELAB-147)\n' for line in (37, 38))
            log.write_text(text, encoding='utf-8')
            inputs = {'candidate_manifest_sha256': sha(root / 'MANIFEST.sha256'), 'top': TOP,
                      'inputs': {str(path): sha(path) for path in (source, package)}}
            summary = {'native_status': {'STAGE': ['reference_top']}, 'run': {'log_sha256': sha(log)}}
            (previous / 'FormalInputs.json').write_text(json.dumps(inputs), encoding='utf-8')
            proof = previous / 'FormalSummary.json'
            proof.write_text(json.dumps(summary), encoding='utf-8')
            result = review_array_warning(previous, root)
            self.assertEqual(result['source_lines'], [37, 38])
            self.assertEqual(result['reachability_proof'], 'NOT_ESTABLISHED')
            self.assertFalse(result['functional_safety_accepted'])
            for changed in (text.replace('Line: 38', 'Line: 39'), text + '\nFMR_ELAB-999\n'):
                log.write_text(changed, encoding='utf-8')
                summary['run']['log_sha256'] = sha(log)
                proof.write_text(json.dumps(summary), encoding='utf-8')
                with self.assertRaises(ValueError):
                    review_array_warning(previous, root)
            log.write_text(text, encoding='utf-8')
            summary['run']['log_sha256'] = sha(log)
            proof.write_text(json.dumps(summary), encoding='utf-8')
            source.write_text('// modified source', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'does not match'):
                review_array_warning(previous, root)


if __name__ == '__main__':
    unittest.main()
