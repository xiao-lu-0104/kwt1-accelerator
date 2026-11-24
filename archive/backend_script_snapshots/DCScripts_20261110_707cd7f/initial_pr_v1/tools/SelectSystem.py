import json
from pathlib import Path
from SystemFlow import REV,sha,verify_manifest,check_hashes,validate_system

def select_system(soc, expected_package):
    choices = []
    for flow in soc.glob('tpusoc_system_dc_20261110_707cd7f_*'):
        progress = flow / 'FlowProgress.json'
        if not progress.is_file():
            continue
        data = json.loads(progress.read_text())
        if data.get('result') == 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING' and data.get('inputs_unchanged') is True:
            choices.append(flow)
    if len(choices) != 1:
        raise ValueError('Expected exactly one successful new 707cd7f system flow, found ' + str(len(choices)))
    flow = choices[0]
    verify_manifest(flow, 'PACKAGE.sha256', expected_package)
    progress = json.loads((flow / 'FlowProgress.json').read_text())
    if progress.get('source_commit') != REV or progress.get('successful_stages') != [
            'hold_structure_review', 'hold_native_incremental_equivalence', 'system_inputs_frozen', 'e203_system_dc_reports']:
        raise ValueError('New system source/stage chain mismatch')
    if json.loads((flow / 'SourceUnchanged.json').read_text()).get('unchanged') is not True:
        raise ValueError('System flow input integrity incomplete')
    system = flow / 'system'
    inputs = json.loads((system / 'SystemInputs.json').read_text())
    check_hashes(inputs['sha256'])
    if inputs.get('source_commit') != REV or Path(inputs['accelerator_run']).name != 'tpusoc_hold_recovery_20261110_707cd7f_Bwf2gR':
        raise ValueError('System accelerator provenance mismatch')
    outputs = json.loads((system / 'SystemOutputs.json').read_text())
    check_hashes({str(system / 'mapped' / name): h for name, h in outputs.items()})
    result = json.loads((system / 'SystemSummary.json').read_text())
    if result.get('result') != 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING' or result.get('original_inputs_unchanged') is not True:
        raise ValueError('System result incomplete')
    validate_system(result['summary'])
    print('CURRENT_SYSTEM_SUMMARY:', json.dumps(result['summary'], sort_keys=True), flush=True)
    print('CURRENT_SYSTEM_AREAS:\n' + (system / 'mapped/area_breakdown.tsv').read_text(), flush=True)
    if result['summary']['SETUP_STATUS'] != 'PASS' or result['summary']['HOLD_STATUS'] != 'PASS':
        raise ValueError('Current system timing is not PASS; review system reports before task power')
    return flow, system, inputs, outputs


