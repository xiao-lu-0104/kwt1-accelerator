"""Build two real reference libraries and import the frozen accelerator into ICC2.

Only reference-library preparation, netlist linking, logical PG connections and
initial floorplan creation are attempted. No placement, CTS, routing or signoff.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import sys
import tarfile

from Formal import TOP, NETLIST_SHA, read_status, tcl_list, script_flag
from Preflight import sha, save_json, command, terminate, load_candidate, structural_references, json_worker

HERE = Path(__file__).resolve().parent
SUCCESS = 'ICC2_IMPORT_AND_INITIAL_FLOORPLAN_COMPLETE_REVIEW_PENDING'


def verified_formal(directory):
    inputs = json.loads((directory / 'FormalInputs.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'FormalSummary.json').read_text(encoding='utf-8'))
    status = summary['native_status']
    if (summary['status'] != 'TOOL_VERIFY_TRUE_INTERPRETATION_REVIEW_PENDING' or
            not summary.get('frozen_candidate_unchanged') or inputs['top'] != TOP or
            any(status.get(key) != ['1'] for key in ('GUIDANCE_READ_RETURN', 'MATCH_RETURN', 'VERIFY_RETURN')) or
            summary['run']['exit_code'] != 0 or summary['run']['status'] != 'EXIT_0' or
            sha(directory / 'fm_actual.log') != summary['run']['log_sha256']):
        raise ValueError('An unchanged actual accelerator Formality verify=1 run is required')
    for name, expected in inputs['inputs'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Passed formal input changed: ' + name)
    if sha(Path(inputs['implementation_netlist'])) != NETLIST_SHA:
        raise ValueError('Passed implementation is not the frozen accelerator')
    return inputs, summary


def choose_formal(home=None):
    for path in sorted(((home or Path.home()) / 'soc').glob('tpusoc_formal_accelerator_20261108_*'),
                       key=lambda p: p.stat().st_mtime, reverse=True):
        if not (path / 'FormalSummary.json').is_file():
            continue
        try:
            inputs, summary = verified_formal(path)
            return path, inputs, summary
        except (OSError, ValueError, KeyError) as error:
            print('PR_FORMAL_CANDIDATE_SKIPPED:', str(path), str(error), flush=True)
    raise ValueError('No unchanged passed accelerator Formality run found')


def within(path, root):
    return root.resolve() in path.resolve().parents


def unique(paths, label):
    paths = sorted(set(Path(path) for path in paths))
    if len(paths) != 1:
        raise ValueError(label + ': expected one candidate; found ' + str(len(paths)) + ' ' + str([str(p) for p in paths]))
    return paths[0]


def geometry_variant(paths):
    paths = sorted(set(Path(p) for p in paths))
    if len(paths) == 2 and paths[0].parent == paths[1].parent:
        plain = [p for p in paths if not p.name.endswith('_ant.lef')]
        if len(plain) == 1 and plain[0].with_name(plain[0].stem + '_ant.lef') in paths:
            enhanced = plain[0].with_name(plain[0].stem + '_ant.lef')
            return enhanced, {'regular': str(plain[0]), 'antenna': str(enhanced), 'status': 'CONTENT_CHECK_REQUIRED'}
    return unique(paths, 'RVT LEF covering every used standard-cell reference'), None


def select_physical(record, std_db, netlist):
    # Fixed engineering trial: the PDK's RVT 8lm_1tm stack identifier.
    # Filename association is followed by native TF/LEF workspace validation.
    std_root = std_db.parents[2]
    if '_RVT' not in str(std_root).upper():
        raise ValueError('Current synthesis library is not the expected RVT family')
    physical = record['physical']
    references = structural_references(netlist.read_text(encoding='utf-8', errors='replace'))
    if not references or 'RAMSP1024X16' not in references or 'RAMSP4096X16' in references:
        raise ValueError('Expected the accelerator-only netlist with private SRAM')
    std_refs = set(references) - {'RAMSP1024X16'}
    choices = None
    for ref in sorted(std_refs):
        paths = {Path(p) for p in physical['lef_definitions'].get(ref, []) if within(Path(p), std_root)}
        choices = paths if choices is None else choices & paths
    geometry, variant = geometry_variant(choices or [])
    technology = unique([a['path'] for a in record['assets']
                         if a['kind'] == 'TECH_OR_RC_CANDIDATE' and within(Path(a['path']), std_root)
                         and Path(a['path']).name.lower() == 'scc40nll_vhs_8lm_1tm.tf'], 'RVT 8lm_1tm TF')
    tech_lef = unique([p for p in physical['technology_lef_candidates'] if within(Path(p), std_root)
                       and Path(p).name.lower() == 'scc40nll_8lm_1tm.lef'], 'RVT 8lm_1tm technology LEF')
    macro = unique(physical['lef_definitions'].get('RAMSP1024X16', []), 'Private SRAM LEF')
    if macro == geometry or geometry == tech_lef:
        raise ValueError('Unexpectedly overlapping physical views')
    # Record the possible RC tables, but do not load one without the layer map.
    rc = [a['path'] for a in record['assets'] if within(Path(a['path']), std_root)
          and '1p8m_1tm' in Path(a['path']).name.lower()
          and Path(a['path']).suffix.lower() in ('.tluplus', '.tlu_plus')]
    return {'std_root': str(std_root), 'technology': str(technology), 'tech_lef': str(tech_lef),
            'std_lef': str(geometry), 'macro_lef': str(macro), 'used_std_refs': sorted(std_refs),
            'rc_candidates_not_loaded': sorted(rc), 'metal_stack': '8lm_1tm',
            'rc_status': 'LAYER_MAPPING_AND_THICKNESS_NOT_VALIDATED_NO_TIMING_SIGNOFF',
            'existing_io_ndm_used': False, 'std_lef_variant': variant}


def pg_names(std_info, macro_info, std_refs):
    cells = [std_info['macros'][ref] for ref in std_refs] + [macro_info['macros']['RAMSP1024X16']]
    power = sorted({name for cell in cells for name, p in cell['pins'].items() if p['use'] == 'POWER'})
    ground = sorted({name for cell in cells for name, p in cell['pins'].items() if p['use'] == 'GROUND'})
    if (not power or not ground or not set(power) <= {'VDD', 'VDDCE', 'VDDPE'} or
            not set(ground) <= {'VSS', 'VSSE'}):
        raise ValueError('PG rail mapping needs review: power=' + str(power) + ' ground=' + str(ground))
    for cell in cells:
        uses = {p['use'] for p in cell['pins'].values()}
        if not {'POWER', 'GROUND'} <= uses:
            raise ValueError('A used physical cell lacks explicit POWER/GROUND LEF pins')
    return power, ground


def stage_result(run, status, expected, artifacts=()):
    errors = []
    path = Path(run['log'])
    if path.is_file():
        errors = [line for line in path.read_text(encoding='utf-8', errors='replace').splitlines()
                  if re.match(r'^\s*Error:', line)]
    success = (run['exit_code'] == 0 and run['status'] == 'EXIT_0' and
               status.get('RESULT') == [expected] and not errors and all(Path(p).exists() for p in artifacts))
    return {'status': expected if success else 'NATIVE_STAGE_FAILED_OR_INCOMPLETE',
            'success': success, 'run': run, 'native_status': status, 'native_errors': errors[:20]}


def scalar(name, value):
    tcl_list([value])
    return 'set ' + name + ' {' + str(value) + '}\n'


def library_check_evidence(stage, status):
    """Independently validate saved native reports, including an empty Tcl return."""
    reports, hashes = {}, {}
    for name in ('check_workspace', 'report_design_mismatch'):
        path = stage / (name + '.rpt')
        if not path.is_file():
            return {'accepted': False, 'reason': 'Missing native report: ' + name}
        reports[name] = path.read_text(encoding='utf-8', errors='replace')
        hashes[path.name] = sha(path)
    accepted = (status.get('MISMATCH_POLICY') == ['default'] and
                status.get('CHECK_WORKSPACE_RETURN') in ([''], ['1'], ['true'], ['TRUE']) and
                status.get('CHECK_WORKSPACE_ACCEPTED') == ['1'] and
                status.get('CHECK_WORKSPACE_EVIDENCE') == ['NATIVE_SUCCESS_AND_NO_DESIGN_MISMATCHES'] and
                re.search(r'^\s*Workspace check succeeded!\s*$', reports['check_workspace'], re.M) is not None and
                re.search(r'^\s*No mismatches exist on the design\.\s*$', reports['report_design_mismatch'], re.M) is not None and
                not any(re.search(r'^\s*(?:Error|Fatal):', text, re.M | re.I) for text in reports.values()))
    return {'accepted': bool(accepted), 'report_sha256': hashes,
            'fram_066_warning_count': len(re.findall(r'\(FRAM-066\)', reports['check_workspace'])),
            'warning_review': 'Preserved native warnings; routing accessibility still requires physical-stage review'}


def prepare(out):
    formal, formal_inputs, formal_summary = choose_formal()
    preflight = Path(formal_inputs['preflight'])
    record_path = preflight / 'BackendPreflight.json'
    record = json.loads(record_path.read_text(encoding='utf-8'))
    if record['status'] != 'FINAL_BACKEND_PREFLIGHT_COLLECTED':
        raise ValueError('Completed physical inventory is required')
    root, originals, frozen = load_candidate(Path(record['source']['source']), out)
    if record['source'] != frozen or sha(root / 'MANIFEST.sha256') != formal_inputs['candidate_manifest_sha256']:
        raise ValueError('Physical preflight, passed formal run and frozen candidate differ')
    netlist = Path(formal_inputs['implementation_netlist'])
    std_db, private_db = [Path(p) for p in formal_inputs['libraries']]
    selected = select_physical(record, std_db, netlist)
    save_json(out / 'PhysicalSelection.json', selected)
    expected = {item['path']: item['sha256'] for item in record['physical']['lef_evidence']}
    variant_paths = []
    if selected['std_lef_variant']:
        pair = selected['std_lef_variant']
        variant_paths = [Path(pair['regular']), Path(pair['antenna'])]
        proof_path = out / 'LefVariantReview.json'
        run = command([sys.executable, '-B', str(HERE / 'LefVariants.py'),
                       '--regular', pair['regular'], '--antenna', pair['antenna'],
                       '--regular-sha', expected[pair['regular']], '--antenna-sha', expected[pair['antenna']],
                       '--output', str(proof_path)], out, 'lef_variant_review', 25)
        review = json.loads(proof_path.read_text(encoding='utf-8')) if proof_path.is_file() else {}
        if run['exit_code'] != 0 or review.get('status') != 'NON_ANTENNA_TOKENS_IDENTICAL':
            raise ValueError('Plain/antenna LEF pair review failed: ' + json.dumps(review, sort_keys=True))
        selected['std_lef_variant'] = review
        save_json(out / 'PhysicalSelection.json', selected)
        print('PR_LEF_VARIANT:', review['status'], 'selected=' + review['selected'], flush=True)
    # Bind the original accelerator SDC to the already-frozen material archive.
    base = Path(frozen['base'])
    system_path = base / 'SystemBaseInputs.json'
    system = json.loads(system_path.read_text(encoding='utf-8'))
    existing = base / 'ExistingMaterials.partial.tar.gz'
    if system['inputs'].get(str(existing)) != sha(existing):
        raise ValueError('Historical accelerator material archive changed')
    sdc = Path(formal_inputs['guidance']['original_synthesis']) / 'mapped/candidate.sdc'
    with tarfile.open(existing, 'r:gz') as stream:
        saved = stream.extractfile('ExistingMaterials/AcceleratorMapping/candidate.sdc')
        if saved is None or saved.read() != sdc.read_bytes():
            raise ValueError('Accelerator SDC differs from its archived original')
    inspected = {}
    for label in ('tech_lef', 'std_lef', 'macro_lef'):
        path = Path(selected[label])
        if expected.get(str(path)) != sha(path):
            raise ValueError('Previously inspected LEF changed: ' + str(path))
        value, run = json_worker(out, 'pr_' + label, ['--worker-inspect-lef', str(path)], 15)
        if not value or value.get('error') or run['exit_code'] != 0 or value.get('sha256') != expected[str(path)]:
            raise ValueError('Selected LEF inspection failed: ' + label)
        inspected[label] = value['info']
    if not set(selected['used_std_refs']) <= set(inspected['std_lef']['macros']):
        raise ValueError('Fresh standard LEF inspection does not cover the accelerator references')
    macro = inspected['macro_lef']['macros']['RAMSP1024X16']
    size = macro.get('size_um')
    if not size or abs(size[0] * size[1] - 9148.524700) > 0.02:
        raise ValueError('Private macro LEF footprint differs from the reviewed synthesis macro')
    power, ground = pg_names(inspected['std_lef'], inspected['macro_lef'], selected['used_std_refs'])
    icc2 = Path(record['tools']['icc2_shell']['executable'])
    lm = icc2.with_name('icc2_lm_shell')
    if not icc2.is_file() or not os.access(str(icc2), os.X_OK) or not lm.is_file() or not os.access(str(lm), os.X_OK):
        raise ValueError('ICC2 and its sibling icc2_lm_shell executables are required; checked ' + str(lm))
    flag = script_flag((preflight / 'icc2_shell_help.log').read_text(encoding='utf-8', errors='replace'))
    help_run = command([str(lm), '-help'], out, 'lm_help', 25)
    if help_run['status'] == 'TIMEOUT':
        raise ValueError('Library Manager help timed out')
    lm_flag = script_flag((out / 'lm_help.log').read_text(encoding='utf-8', errors='replace'))
    paths = [netlist, sdc, std_db, private_db, Path(selected['technology'])] + [Path(selected[k]) for k in ('tech_lef', 'std_lef', 'macro_lef')]
    paths += [formal / 'FormalInputs.json', formal / 'FormalSummary.json', record_path, system_path, existing,
              preflight / 'icc2_shell_help.log', out / 'PhysicalSelection.json']
    paths += [p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py', '.tcl')]
    paths += variant_paths
    if variant_paths:
        paths.append(out / 'LefVariantReview.json')
    inputs = {str(p): sha(p) for p in paths}
    result = {'status': 'ICC2_START_PREPARED', 'formal_source': str(formal), 'formal_result': formal_summary['status'],
              'preflight': str(preflight), 'candidate': str(root), 'inputs': inputs, 'selection': selected,
              'netlist': str(netlist), 'sdc': str(sdc), 'std_db': str(std_db), 'private_db': str(private_db),
              'power_pins': power, 'ground_pins': ground, 'icc2': str(icc2), 'lm': str(lm),
              'icc2_flag': flag, 'lm_flag': lm_flag, 'limits': {'library_each_seconds': 600, 'import_seconds': 600},
              'scope': 'NICE/TPU/DMA/ICB plus 56 private macros; CPU/shared TCM excluded',
              'formal_limitations': 'Array-index safety and macro/guidance review remain pending; no full-system proof',
              'output_limitations': 'Initial floorplan only; macro placement, PG straps, RC, CTS, routing and signoff not performed'}
    save_json(out / 'PrInputs.json', result)
    print('PR_INPUTS_VERIFIED:', 'passed_formal=' + str(formal), 'stack=RVT_8lm_1tm', flush=True)
    print('PR_TECHNOLOGY:', selected['technology'], flush=True)
    print('PR_REFERENCE_LEFS:', selected['std_lef'], selected['macro_lef'], flush=True)
    return root, originals, result


def run_libraries(out, inputs):
    ndms, results = [], {}
    for label, db, lef in (('rvt', inputs['std_db'], inputs['selection']['std_lef']),
                           ('private', inputs['private_db'], inputs['selection']['macro_lef'])):
        stage = out / ('library_' + label)
        stage.mkdir()
        ndm = stage / (label + '.ndm')
        config = (scalar('PrTechnology', inputs['selection']['technology']) + scalar('PrWorkspace', label) +
                  scalar('PrDb', db) + scalar('PrNdm', ndm) +
                  'set PrLefs ' + tcl_list([inputs['selection']['tech_lef'], lef]) + '\n')
        config_path = stage / 'PrLibraryConfig.tcl'
        config_path.write_text(config, encoding='utf-8')
        inputs['inputs'][str(config_path)] = sha(config_path)
        save_json(out / 'PrInputs.json', inputs)
        run = command([inputs['lm'], inputs['lm_flag'], str(HERE / 'PrLibrary.tcl')], stage, 'lm_actual', 600)
        status = read_status(stage / 'PrStatus.tsv')
        result = stage_result(run, status, 'REFERENCE_LIBRARY_CREATED_REVIEW_PENDING', [ndm])
        evidence = library_check_evidence(stage, status)
        result['workspace_check_evidence'] = evidence
        if not evidence['accepted']:
            result.update(success=False, status='NATIVE_LIBRARY_CHECK_NOT_ACCEPTED')
        results[label] = result
        save_json(out / 'PrLibraryResults.json', results)
        if not result['success']:
            return [], results
        ndms.append(ndm)
    return ndms, results


def run_import(out, inputs, ndms):
    stage = out / 'design'
    stage.mkdir()
    definition = stage / 'initial_floorplan.def'
    lib = stage / 'accelerator.nlib'
    config = ''.join(scalar(name, value) for name, value in (
        ('PrTechnology', inputs['selection']['technology']), ('PrDesignLib', lib), ('PrTop', TOP),
        ('PrNetlist', inputs['netlist']), ('PrSdc', inputs['sdc']), ('PrDef', definition)))
    config += 'set PrRefLibs ' + tcl_list(ndms) + '\n'
    config += 'set PrPowerPins ' + tcl_list(inputs['power_pins']) + '\n'
    config += 'set PrGroundPins ' + tcl_list(inputs['ground_pins']) + '\n'
    config_path = stage / 'PrImportConfig.tcl'
    config_path.write_text(config, encoding='utf-8')
    inputs['inputs'][str(config_path)] = sha(config_path)
    save_json(out / 'PrInputs.json', inputs)
    run = command([inputs['icc2'], inputs['icc2_flag'], str(HERE / 'PrImport.tcl')], stage, 'icc2_actual', 600)
    status = read_status(stage / 'PrStatus.tsv')
    result = stage_result(run, status, SUCCESS, [definition, lib])
    if status.get('PRIVATE_MACROS') != ['56'] or status.get('UNBOUND_CELLS') != ['0']:
        result.update(success=False, status='ICC2_IMPORT_COUNTS_NOT_ACCEPTED')
    result['design_library'] = str(lib)
    result['floorplan_def'] = str(definition)
    save_json(out / 'PrImportResult.json', result)
    return result


def finish(out, inputs, libraries, imported, error=None):
    unchanged = True if inputs.get('inputs') else None
    for name, expected in inputs.get('inputs', {}).items():
        try:
            same = sha(Path(name)) == expected
        except OSError:
            same = False
        if not same:
            unchanged = False
            error = 'Input changed during actual PR stage: ' + name
    success = bool(imported and imported['success'] and unchanged and not error)
    result = {'status': SUCCESS if success else 'ICC2_START_INCOMPLETE_REVIEW_LOGS',
              'libraries': libraries, 'import': imported, 'error': error, 'inputs_unchanged': unchanged,
              'scope': inputs.get('scope'), 'limitations': inputs.get('output_limitations'),
              'actual_placement_cts_routing': 'NOT_RUN', 'rc_timing_signoff': 'NOT_RUN'}
    save_json(out / 'PrSummary.json', result)
    selected = []
    for parent, directories, names in os.walk(out):
        directories[:] = sorted(name for name in directories if not name.endswith(('.ndm', '.nlib'))
                                and not (Path(parent) / name).is_symlink())
        for name in sorted(names):
            p = Path(parent) / name
            if (p.is_file() and not p.is_symlink() and p.suffix in
                    ('.py', '.tcl', '.json', '.tsv', '.rpt', '.log', '.txt', '.def') and
                    name not in ('runner.log', 'pr_runner.log')):
                selected.append(p)
    package = out / 'PrStartReports.partial.tar.gz'
    with tarfile.open(package, 'x:gz') as stream:
        for path in selected:
            stream.add(path, arcname='PrStartReports/' + path.relative_to(out).as_posix(), recursive=False)
    (out / 'PrStartReports.sha256').write_text(sha(package) + '  ' + package.name + '\n', encoding='utf-8')
    for label, stage in list(libraries.items()) + ([('import', imported)] if imported else []):
        print('PR_NATIVE_STAGE:', label, stage['status'], flush=True)
        print('PR_NATIVE_STATUS:', json.dumps(stage['native_status'], sort_keys=True), flush=True)
        if 'workspace_check_evidence' in stage:
            print('PR_WORKSPACE_EVIDENCE:', label, json.dumps(stage['workspace_check_evidence'], sort_keys=True), flush=True)
        if not stage['success']:
            lines = Path(stage['run']['log']).read_text(encoding='utf-8', errors='replace').splitlines()
            print('PR_NATIVE_ERRORS:', '\n'.join(stage.get('native_errors', [])), flush=True)
            print('PR_NATIVE_LOG_TAIL:', '\n'.join(lines[-16:]), flush=True)
            for name in ('check_workspace.rpt', 'report_design_mismatch.rpt'):
                report = Path(stage['run']['log']).parent / name
                if report.is_file():
                    tail = report.read_text(encoding='utf-8', errors='replace').splitlines()[-12:]
                    print('PR_NATIVE_REPORT_TAIL:', label, name, '\n' + '\n'.join(tail), flush=True)
    if error:
        print('PR_ERROR:', error, flush=True)
    if imported:
        print('PR_DESIGN_LIBRARY:', imported['design_library'], flush=True)
        print('PR_INITIAL_DEF:', imported['floorplan_def'], flush=True)
    print('PR_INPUTS_UNCHANGED:', unchanged, flush=True)
    print('PR_REPORT_ARCHIVE:', str(package), flush=True)
    print('PR_SCOPE: accelerator + 56 private macros; macro placement/RC/PG routing/CTS/route/signoff remain pending', flush=True)
    print('RESULT:', result['status'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, terminate)
    inputs, libraries, imported, error = {}, {}, None, None
    try:
        root, originals, inputs = prepare(out)
        ndms, libraries = run_libraries(out, inputs)
        if ndms:
            imported = run_import(out, inputs, ndms)
        from InitialMaterials import verify
        if verify(root) != originals:
            raise ValueError('Frozen candidate changed during PR preparation')
    except (OSError, ValueError, KeyError) as why:
        error = str(why)
    finish(out, inputs, libraries, imported, error)


if __name__ == '__main__':
    main()
