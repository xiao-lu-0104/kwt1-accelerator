"""Run actual accelerator Formality against the frozen mapped checkpoint.

Tool success is retained separately from review of compare points, unmatched points,
and macro boundaries. The SRAM's transistor/behavioral semantics are not proved here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import tarfile

from Preflight import sha, load_candidate, command, save_json, terminate

TOP = 'e203_subsys_nice_core'
BUNDLE_SHA = 'baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83'
NETLIST_SHA = 'b366417d57d6251f13a827933288886637b61071472d391b121a7341fa2ea75e'
RTL = ('TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer '
       'TpuMatmul TpuGelu TpuVector TpuDma TpuTop TpuNice TpuIcb').split()


def tcl_list(values):
    values = [str(value) for value in values]
    if any(any(char in value for char in '{}\r\n\\') for value in values):
        raise ValueError('Unsafe Tcl path')
    return '[list ' + ' '.join('{' + value + '}' for value in values) + ']'


def script_flag(text):
    for flag in ('-f', '-file'):
        if re.search(r'(?:^|[\s\[])' + re.escape(flag) + r'(?=[\s,\]])', text):
            return flag
    raise ValueError('Installed tool help has no confirmed script-file option')


def clean_manual(text):
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
    while '\b' in text:
        previous = text
        text = re.sub(r'.\x08', '', text)
        if text == previous:
            break
    return text


def manual_section(text, name):
    text = clean_manual(text)
    marker = 'FORMAL_COMMAND_MANUAL: ' + name
    if text.count(marker) != 1:
        raise ValueError('Missing or ambiguous installed manual for ' + name)
    section = text.split(marker, 1)[1].split('FORMAL_COMMAND_MANUAL:', 1)[0]
    if 'SYNTAX' not in section:
        raise ValueError('Incomplete installed manual for ' + name)
    return section


def validated_sources(root, manifest):
    if sha(manifest) != BUNDLE_SHA:
        raise ValueError('Original synthesis-source bundle manifest changed')
    entries = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        if name in entries:
            raise ValueError('Duplicate original bundle manifest entry')
        entries[name] = digest
    names = ['Rtl/' + name + '.sv' for name in RTL]
    names += ['Backend/' + TOP + '.sv', 'Server/Backend/SpFoundry.sv']
    sources = [root / 'Project' / name for name in names]
    for name, path in zip(names, sources):
        if name not in entries or sha(path) != entries[name]:
            raise ValueError('Reference RTL differs from original synthesis source: ' + name)
    return sources


def array_warning_locations(text, expected_file):
    locations = []
    for line in text.splitlines():
        if not line.startswith('Warning:') or '(FMR_ELAB-147)' not in line:
            continue
        match = re.search(r'Index may take values outside array bound.*?Signal:\s*RegionData\s+Block:\s*/TpuSram\s+File:\s*(.*?)\s+Line:\s*(\d+)\)', line)
        if not match or Path(match[1]).resolve() != expected_file.resolve() or int(match[2]) not in (37, 38):
            raise ValueError('Additional or changed FMR_ELAB-147 warning requires separate review')
        locations.append(int(match[2]))
    if set(locations) != {37, 38}:
        raise ValueError('Both reviewed RegionData warning locations must be present')
    return locations


def review_array_warning(previous, root):
    prior_inputs = json.loads((previous / 'FormalInputs.json').read_text(encoding='utf-8'))
    prior_summary = json.loads((previous / 'FormalSummary.json').read_text(encoding='utf-8'))
    source = root / 'Project/Rtl/TpuSram.sv'
    package = root / 'Project/Rtl/TpuPkg.sv'
    if (prior_inputs.get('candidate_manifest_sha256') != sha(root / 'MANIFEST.sha256') or
            prior_inputs.get('inputs', {}).get(str(source)) != sha(source) or
            prior_inputs.get('inputs', {}).get(str(package)) != sha(package) or
            prior_inputs.get('top') != TOP or
            prior_summary.get('native_status', {}).get('STAGE', [])[-1:] != ['reference_top']):
        raise ValueError('Warning evidence does not match this frozen RTL and failed link stage')
    log = previous / 'fm_actual.log'
    text = log.read_text(encoding='utf-8', errors='replace')
    if sha(log) != prior_summary['run']['log_sha256']:
        raise ValueError('Prior formal diagnostic log changed')
    codes = set(re.findall(r'FMR_ELAB-\d+', text))
    if codes != {'FMR_ELAB-147'}:
        raise ValueError('Other RTL interpretation messages require separate review')
    locations = array_warning_locations(text, source)
    lines = source.read_text(encoding='utf-8').splitlines()
    for line, port, select in ((37, 'A', 'SelectA'), (38, 'B', 'SelectB')):
        expected = "SramRead" + port + "Data <= RegionData[$clog2(Regions)'(" + select + ")];"
        if lines[line - 1].strip() != expected:
            raise ValueError('Reviewed array expression differs from frozen source')
    if not re.search(r'`ifdef\s+TPU_LEGACY_STORAGE\s+localparam int Regions = 16;\s+`else\s+localparam int Regions = 7;',
                     package.read_text(encoding='utf-8')):
        raise ValueError('Unexpected storage-region configuration')
    return {'status': 'ACKNOWLEDGED_FOR_DIAGNOSTIC_COMPARISON_ONLY', 'message_id': 'FMR_ELAB-147',
            'previous_run': str(previous), 'log_sha256': sha(log), 'source': str(source),
            'source_sha256': sha(source), 'source_lines': sorted(set(locations)),
            'regions': 7, 'valid_region_indices': [0, 6], 'selector_bits': 3,
            'potential_invalid_index': 7, 'reachability_proof': 'NOT_ESTABLISHED',
            'state_initialization': 'SelectA/SelectB are not reset; no zero/reset assumptions added',
            'action': 'set_mismatch_message_filter -warn FMR_ELAB-147; keep native warnings visible',
            'scope': 'Only the two identified RegionData array reads; extra locations fail review',
            'rtl_changed': False, 'netlist_changed': False, 'functional_safety_accepted': False,
            'meaning': 'Permits linking and an actual comparison; it does not prove index safety or waive compare points'}


def find_array_review(root, home=None):
    parent = (home or Path.home()) / 'soc'
    for previous in sorted(parent.glob('tpusoc_formal_accelerator_20261108_*'), key=lambda p: p.stat().st_mtime, reverse=True):
        if not (previous / 'FormalSummary.json').is_file():
            continue
        try:
            return review_array_warning(previous, root)
        except (OSError, ValueError, KeyError):
            continue
    raise ValueError('Unchanged native evidence for the two reviewed FMR_ELAB-147 warnings is required')


def validated_guidance(original, sources, libraries, out):
    """Bind an SVF candidate to the original synthesis directory and exact inputs.

    This is filesystem provenance, not proof that every SVF operation is valid.
    Native guidance acceptance/rejection and actual verification remain required.
    """
    netlist = original / 'mapped/candidate.v'
    if sha(netlist) != NETLIST_SHA:
        raise ValueError('Guidance directory netlist differs from the frozen accelerator')
    evidence_path = original / 'source/Evidence.json'
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    expected = {path.name: sha(path) for path in sources}
    if (evidence.get('top') != TOP or evidence.get('bundle_manifest_sha256') != BUNDLE_SHA or
            evidence.get('source_sha256') != expected):
        raise ValueError('Guidance directory source evidence differs from the reference RTL')
    tracked = {str(netlist): sha(netlist), str(evidence_path): sha(evidence_path)}
    for name, digest in expected.items():
        path = original / 'source' / name
        if sha(path) != digest:
            raise ValueError('Original synthesis source changed: ' + name)
        tracked[str(path)] = digest
    ledger = original / 'library_sha256.txt'
    entries = [line.split('  ', 1) for line in ledger.read_text(encoding='utf-8').splitlines() if line]
    if len(entries) != len(libraries) or {name: digest for digest, name in entries} != {str(p): sha(p) for p in libraries}:
        raise ValueError('Guidance synthesis libraries differ from the current comparison libraries')
    tracked[str(ledger)] = sha(ledger)
    candidates = sorted(p for directory in (original, original / 'mapped') for p in directory.glob('*.svf')
                        if p.is_file() and not p.is_symlink())
    if len(candidates) != 1:
        raise ValueError('Expected one unambiguous SVF in the original accelerator synthesis directories; found ' + str(len(candidates)))
    svf = candidates[0]
    if not 0 < svf.stat().st_size <= 256 * 1024 * 1024:
        raise ValueError('Original accelerator SVF is empty or exceeds the bounded copy size')
    digest = sha(svf)
    snapshot = out / 'AcceleratorGuidance.svf'
    with svf.open('rb') as source, snapshot.open('xb') as target:
        shutil.copyfileobj(source, target)
    if sha(snapshot) != digest or sha(svf) != digest:
        raise ValueError('Accelerator SVF changed while snapshotting')
    tracked[str(svf)] = tracked[str(snapshot)] = digest
    return {'status': 'SAME_SYNTHESIS_DIRECTORY_WITH_MATCHED_RTL_NETLIST_LIBRARIES',
            'original_synthesis': str(original), 'original_svf': str(svf), 'snapshot': str(snapshot),
            'sha256': digest, 'bytes': snapshot.stat().st_size, 'inputs': tracked,
            'native_guidance_acceptance': 'NOT_YET_CHECKED',
            'limitation': 'SVF was not fingerprinted by the historical run; directory association does not prove its contents',
            'auto_setup': 'DISABLED; no automatic changes to undriven/reset/verification policies'}


def accelerator_guidance(base, sources, libraries, out):
    system_path = base / 'SystemBaseInputs.json'
    system = json.loads(system_path.read_text(encoding='utf-8'))
    task_path = Path(system['source']) / 'TaskPowerInputs.json'
    task = json.loads(task_path.read_text(encoding='utf-8'))
    original = Path(task['paths']['original'])
    proof = validated_guidance(original, sources, libraries, out)
    proof['inputs'].update({str(system_path): sha(system_path), str(task_path): sha(task_path)})
    save_json(out / 'GuidanceProvenance.json', proof)
    print('FORMAL_GUIDANCE_PROVENANCE:', proof['status'], 'original=' + str(original),
          'svf_sha256=' + proof['sha256'], flush=True)
    return proof


def prepare(preflight, out):
    record_path = preflight / 'BackendPreflight.json'
    record = json.loads(record_path.read_text(encoding='utf-8'))
    if record['status'] != 'FINAL_BACKEND_PREFLIGHT_COLLECTED':
        raise ValueError('A completed preflight is required')
    root, originals, frozen = load_candidate(Path(record['source']['source']), out)
    if record['source'] != frozen:
        raise ValueError('Preflight and current verified candidate differ')
    base = Path(frozen['base'])
    netlist = base / 'frozen_accelerator.v'
    if sha(netlist) != NETLIST_SHA:
        raise ValueError('Accelerator netlist differs from the task-verified frozen checkpoint')
    # This fixed manifest identifies the exact RTL used by the earlier synthesis.
    manifest = base / 'ExistingMaterials/SourceBundle/MANIFEST.sha256'
    sources = validated_sources(root, manifest)
    array_review = find_array_review(root)
    review_file = out / 'InterpretationReview.json'
    save_json(review_file, array_review)
    libraries = [Path(frozen['paths'][key]) for key in ('std_db', 'private_db')]
    guidance = accelerator_guidance(base, sources, libraries, out)
    documentation = preflight / 'fm_commands.log'
    text = documentation.read_text(encoding='utf-8', errors='replace')
    for name, required in (('read_verilog', ('-i', '-libname', '-netlist')),
                           ('read_db', ('-technology_library',)), ('set_top', ()), ('set_svf', ())):
        section = manual_section(text, name)
        if any(option not in section for option in required):
            raise ValueError('Installed manual does not confirm ' + name + ' options')
    fm = Path(record['tools']['fm_shell']['executable'])
    if not fm.is_file() or not os.access(str(fm), os.X_OK):
        raise ValueError('Preflight Formality executable is unavailable')
    help_file = preflight / 'fm_shell_help.log'
    flag = script_flag(help_file.read_text(encoding='utf-8', errors='replace'))
    tcl_list([netlist, guidance['snapshot']])  # Validate scalar paths as Tcl data.
    config = ('set FormalTop {' + TOP + '}\nset FormalSources ' + tcl_list(sources) +
              '\nset FormalLibraries ' + tcl_list(libraries) + '\nset FormalNetlist {' + str(netlist) + '}\n' +
              'set FormalReviewedArrayWarning {FMR_ELAB-147}\n' +
              'set FormalSvf {' + guidance['snapshot'] + '}\n')
    (out / 'FormalConfig.tcl').write_text(config, encoding='utf-8')
    inputs = {str(path): sha(path) for path in sources + libraries + [netlist, manifest, record_path, documentation, help_file,
                                                                  out / 'FormalConfig.tcl', review_file]}
    inputs.update(guidance['inputs'])
    inputs[str(out / 'GuidanceProvenance.json')] = sha(out / 'GuidanceProvenance.json')
    for path in Path(__file__).resolve().parent.iterdir():
        if path.is_file():
            inputs[str(path)] = sha(path)
    result = {'status': 'FORMAL_ACCELERATOR_PREPARED', 'preflight': str(preflight), 'candidate': str(root),
              'candidate_manifest_sha256': sha(root / 'MANIFEST.sha256'), 'inputs': inputs,
              'top': TOP, 'reference_sources': [str(path) for path in sources], 'implementation_netlist': str(netlist),
              'libraries': [str(path) for path in libraries], 'executable': str(fm), 'script_flag': flag,
              'defines': ['SYNTHESIS', 'TPU_SRAM_MODEL'], 'guidance': guidance,
              'reference_reader': 'read_sverilog; native installed manual/options checked before use',
              'rtl_interpretation_review': array_review,
              'scope': 'NICE/TPU/DMA/ICB/private SRAM interfaces; CPU/shared TCM excluded',
              'memory_boundary': 'Same real foundry technology DB; compare-point/blackbox review required; macro internals not proved',
              'restrictions': 'No reset constraints, forced state/constants, dont-verify points or extra black boxes'}
    save_json(out / 'FormalInputs.json', result)
    print('FORMAL_INPUTS_VERIFIED:', TOP, 'reference_files=' + str(len(sources)), flush=True)
    return root, originals, result, record


def read_status(path):
    values = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            if '\t' in line:
                key, value = line.split('\t', 1)
                values.setdefault(key, []).append(value)
    return values


def classify(status, run):
    if (run['exit_code'] == 0 and status.get('RESULT') in (['TOOL_VERIFY_TRUE_REVIEW_PENDING'],
                                                         ['TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING'])
            and status.get('VERIFY_RETURN') in (['1'], ['true'], ['TRUE'])):
        return status['RESULT'][0]
    if run['status'] == 'TIMEOUT':
        return 'FORMAL_TIMEOUT_INCONCLUSIVE'
    return 'FORMAL_ATTEMPT_FAILED_OR_INCONCLUSIVE'


def failure_summary(out):
    def content(name):
        path = out / name
        return path.read_text(encoding='utf-8', errors='replace') if path.is_file() else ''
    text = content('report_failing_points.rpt')
    count = re.search(r'(\d+)\s+Failing compare points', text)
    points = re.findall(r'Ref\s+\S+\s+(r:/\S+)', text)
    return {'listed_failing_count': int(count[1]) if count else None,
            'listed_reference_points': points,
            'report_says_no_aborted_points': 'No aborted compare points.' in content('report_aborted_points.rpt'),
            'interpretation': 'Native failed comparisons; root cause is not inferred from register names'}


def diagnostic_files(out):
    # Sessions remain on the server; keep small counterexample files in the report
    # archive. Disclose any omitted files rather than presenting a partial set as full.
    patterns = []
    evidence = out / 'FailureEvidence'
    if evidence.is_dir():
        patterns = [p for p in sorted(evidence.rglob('*')) if p.is_file() and not p.is_symlink()]
    total = sum(p.stat().st_size for p in patterns)
    included = patterns if total <= 64 * 1024 * 1024 else []
    files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in included}
    sessions = [{'path': str(p), 'is_directory': p.is_dir(),
                 'bytes': p.stat().st_size if p.is_file() else None}
                for p in sorted(out.glob('FailureSession*'))]
    return included, {'patterns': files, 'pattern_bytes': total,
                      'pattern_archive_status': 'INCLUDED' if included else ('OVER_64MIB_SERVER_ONLY' if patterns else 'NO_FILES_CREATED'),
                      'sessions_server_only': sessions,
                      'session_restore_not_tested': True}


def icc2_documentation(preflight, out, record):
    tool = record['tools'].get('icc2_shell', {}).get('executable')
    help_file = preflight / 'icc2_shell_help.log'
    if not tool or not help_file.is_file():
        return {'status': 'SKIPPED_MISSING_TOOL_OR_HELP', 'actual_pr': 'NOT_RUN'}
    try:
        flag = script_flag(help_file.read_text(encoding='utf-8', errors='replace'))
    except ValueError:
        return {'status': 'SKIPPED_UNCONFIRMED_SCRIPT_FLAG', 'actual_pr': 'NOT_RUN'}
    probe = out / 'Icc2Documentation.tcl'
    probe.write_text('''# Documentation only: no design import, floorplan or routing.
foreach name {create_lib read_verilog read_lef read_sdc link_block initialize_floorplan create_placement connect_pg_net read_parasitic_tech set_parasitic_parameters save_block write_def write_gds} {
    puts "ICC2_COMMAND_MANUAL: $name"
    if {[catch {man $name} why]} {puts "ICC2_MANUAL_UNAVAILABLE: $name $why"}
}
puts "ICC2_DOCUMENTATION_COMPLETE; PHYSICAL_IMPLEMENTATION_NOT_RUN"
exit
''', encoding='utf-8')
    result = command([tool, flag, str(probe)], out, 'icc2_documentation', 75)
    result['actual_pr'] = 'NOT_RUN'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--preflight', type=Path, required=True)
    args = parser.parse_args()
    out, preflight = args.out.resolve(), args.preflight.resolve()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, terminate)
    try:
        root, originals, inputs, record = prepare(preflight, out)
    except (OSError, ValueError, KeyError) as error:
        save_json(out / 'FormalPreparation.json', {'status': 'FORMAL_NOT_RUN_PREPARATION_FAILED', 'error': str(error)})
        print('FORMAL_PREPARATION_ERROR:', str(error), flush=True)
        print('RESULT: FORMAL_NOT_RUN_PREPARATION_FAILED', flush=True)
        raise SystemExit(2)
    icc2 = icc2_documentation(preflight, out, record)
    save_json(out / 'Icc2Documentation.json', icc2)
    script = Path(__file__).resolve().parent / 'Formal.tcl'
    run = command([inputs['executable'], inputs['script_flag'], str(script)], out, 'fm_actual', 1200)
    status = read_status(out / 'FormalStatus.tsv')
    outcome = classify(status, run)
    warning_validation = 'NOT_REACHED'
    if (out / 'fm_actual.log').is_file():
        log_text = (out / 'fm_actual.log').read_text(encoding='utf-8', errors='replace')
        try:
            array_warning_locations(log_text, root / 'Project/Rtl/TpuSram.sv')
            warning_validation = 'ONLY_REVIEWED_LOCATIONS_OBSERVED'
        except ValueError as error:
            warning_validation = str(error)
            if outcome.startswith('TOOL_VERIFY_TRUE'):
                outcome = 'TOOL_VERIFY_TRUE_UNREVIEWED_INTERPRETATION_WARNING'
    # Even a failed or timed-out run must leave diagnostic reports and a summary.
    for name, expected in inputs['inputs'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Formal input changed during execution: ' + name)
    from InitialMaterials import verify
    if verify(root) != originals:
        raise ValueError('Frozen candidate changed during formal execution')
    reports = {path.name: sha(path) for path in out.glob('*.rpt')}
    patterns, evidence = diagnostic_files(out)
    failures = failure_summary(out)
    result = {'status': outcome, 'run': run, 'native_status': status, 'reports': reports,
              'failure_summary': failures, 'diagnostic_evidence': evidence,
              'guidance_provenance': inputs['guidance'],
              'scope': inputs['scope'], 'icc2_documentation': icc2,
              'final_acceptance': 'PENDING_COMPARE_POINTS_UNMATCHED_AND_MACRO_BOUNDARY_REVIEW',
              'rtl_interpretation_review': inputs['rtl_interpretation_review'],
              'interpretation_warning_validation': warning_validation,
              'array_index_reachability': 'NOT_PROVED',
              'actual_pr': 'NOT_RUN', 'frozen_candidate_unchanged': True}
    save_json(out / 'FormalSummary.json', result)
    package = out / 'FormalReports.partial.tar.gz'
    selected = [path for path in sorted(out.iterdir()) if path.is_file() and path.suffix in ('.rpt', '.tsv', '.json', '.tcl', '.log', '.txt')
                and path.name not in ('runner.log', 'formal_runner.log')]
    selected += [path for path in sorted((out / 'tools').iterdir()) if path.is_file() and path.suffix in ('.py', '.tcl')]
    selected += patterns
    guidance_text = out / 'formality_svf/svf.txt'
    if guidance_text.is_file() and not guidance_text.is_symlink() and guidance_text.stat().st_size <= 64 * 1024 * 1024:
        selected.append(guidance_text)
    with tarfile.open(package, 'x:gz') as stream:
        for path in selected:
            stream.add(path, arcname='FormalReports/' + path.relative_to(out).as_posix(), recursive=False)
    (out / 'FormalReports.sha256').write_text(sha(package) + '  ' + package.name + '\n', encoding='utf-8')
    print('FORMAL_SCOPE:', inputs['scope'], flush=True)
    print('FORMAL_GUIDANCE_READ_RETURN:', status.get('GUIDANCE_READ_RETURN', ['NOT_REACHED'])[-1], flush=True)
    print('FORMAL_GUIDANCE_SHA256:', inputs['guidance']['sha256'], flush=True)
    print('FORMAL_MATCH_RETURN:', status.get('MATCH_RETURN', ['NOT_REACHED'])[-1], flush=True)
    print('FORMAL_VERIFY_RETURN:', status.get('VERIFY_RETURN', ['NOT_REACHED'])[-1], flush=True)
    print('FORMAL_LAST_STAGE:', status.get('STAGE', ['UNKNOWN'])[-1], flush=True)
    print('FORMAL_ARRAY_INDEX_SAFETY: NOT_PROVED; reviewed FMR_ELAB-147 remains an explicit limitation', flush=True)
    print('FORMAL_WARNING_LOCATIONS:', warning_validation, flush=True)
    compact = {key: failures[key] for key in ('listed_failing_count', 'report_says_no_aborted_points')}
    compact['register_names'] = sorted(set(re.sub(r'\[\d+\]$', '', name.rsplit('/', 1)[-1])
                                           for name in failures['listed_reference_points']))
    print('FORMAL_FAILURE_SUMMARY:', json.dumps(compact, sort_keys=True), flush=True)
    print('FORMAL_DIAGNOSTIC_EVIDENCE: pattern_files=' + str(len(patterns)),
          'pattern_archive=' + evidence['pattern_archive_status'],
          'session_paths=' + json.dumps([p['path'] for p in evidence['sessions_server_only']]), flush=True)
    for item in status.get('DIAGNOSTIC_COMPLETE', []) + status.get('DIAGNOSTIC_ERROR', []) + status.get('DIAGNOSTIC_UNAVAILABLE', []):
        print('FORMAL_DIAGNOSTIC:', item, flush=True)
    for error in status.get('ERROR', []):
        print('FORMAL_ERROR:', error, flush=True)
    print('FORMAL_NATIVE_REPORTS:', ' '.join(sorted(reports)), flush=True)
    print('ICC2_DOCUMENTATION_STATUS:', icc2['status'], 'actual_pr=NOT_RUN', flush=True)
    print('FROZEN_CANDIDATE_UNCHANGED: PASS', flush=True)
    print('FORMAL_REPORT_ARCHIVE:', str(package), flush=True)
    print('RESULT:', outcome, '; no final equivalence acceptance or physical implementation claimed', flush=True)
    guidance_report = out / 'guidance_summary.rpt'
    if guidance_report.is_file():
        print('FORMAL_GUIDANCE_SUMMARY_PREVIEW:', flush=True)
        lines = [line for line in guidance_report.read_text(encoding='utf-8', errors='replace').splitlines() if line.strip()]
        print('\n'.join(lines[:28]), flush=True)
    log_lines = (out / 'fm_actual.log').read_text(encoding='utf-8', errors='replace').splitlines()
    errors = [line for line in log_lines if line.startswith('Error:')]
    if errors:
        print('FORMAL_NATIVE_ERRORS:', flush=True)
        print('\n'.join(errors[:6]), flush=True)
    if not outcome.startswith('TOOL_VERIFY_TRUE'):
        lines = (out / 'fm_actual.log').read_text(encoding='utf-8', errors='replace').splitlines()
        print('FORMAL_LOG_TAIL:', flush=True)
        print('\n'.join(lines[-12:]), flush=True)
        for name in ('report_analysis_results.rpt', 'analyze_points.rpt'):
            path = out / name
            if path.is_file():
                lines = [line for line in path.read_text(encoding='utf-8', errors='replace').splitlines() if line.strip()]
                print('FORMAL_NATIVE_ANALYSIS_PREVIEW:', name, flush=True)
                print('\n'.join(lines[:24]), flush=True)


if __name__ == '__main__':
    main()
