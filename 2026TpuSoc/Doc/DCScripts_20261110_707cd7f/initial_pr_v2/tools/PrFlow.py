"""Fresh 707cd7f ICC2 import/initial placement; historical physical refs only."""
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
from PrHelpers import geometry, native, save, scalar, serialized_clock, sha, tlist, tree, verify
from Preflight import lef_info, structural_references
from SystemFlow import REV, check_hashes, verify_manifest
from SelectSystem import select_system
from PinPlan import validate as validate_io

HERE = Path(__file__).resolve().parent


def physical_references(soc):
    choices = []
    for source in soc.glob('tpusoc_system_pr_resume_20261109_*'):
        path = source / 'NewPrSummary.json'
        if not path.is_file():
            continue
        d = json.loads(path.read_text())
        if d.get('result') == 'NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING' and d.get('original_inputs_unchanged') is True:
            choices.append(source)
    if len(choices) != 1:
        raise ValueError('Expected one verified old reference-library source; do not select an old design')
    source = choices[0]
    record = json.loads((source / 'PrRecoveryInputs.json').read_text())
    snapshots = record['reference_snapshots']
    references = {}
    for label in ('rvt', 'private', 'shared'):
        expected = [v for p, v in snapshots.items() if Path(p).name == label + '.ndm']
        path = source / ('library_' + label) / (label + '.ndm')
        if len(expected) != 1 or tree(path) != expected[0]:
            raise ValueError('Historical physical reference differs from verified snapshot: ' + str(path))
        references[label] = (path, expected[0])
    physical_path = soc / 'tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json'
    physical = json.loads(physical_path.read_text())
    selected = physical['selection']
    for key in ('technology', 'tech_lef', 'std_lef', 'macro_lef'):
        path = Path(selected[key])
        if str(path) not in physical['inputs']:
            raise ValueError('Technology/LEF missing from reviewed original ledger: ' + str(path))
        check_hashes({str(path): physical['inputs'][str(path)]})
    return source, references, physical, physical_path


def main(out):
    config = json.loads((out / 'Config.json').read_text())
    soc = Path.home() / 'soc'
    flow, system, system_inputs, outputs = select_system(soc, config['system_package_sha256'])
    powers = []
    for p in soc.glob('tpusoc_task_power_20261110_707cd7f_*'):
        result = p / 'CurrentPowerSummary.json'
        if result.is_file() and json.loads(result.read_text()).get('result') == 'CURRENT_SYSTEM_TASK_POWER_REPORTS_COMPLETE_REVIEW_PENDING':
            powers.append(p)
    if len(powers) != 1:
        raise ValueError('Expected exactly one completed new power run')
    power = powers[0]
    verify_manifest(power, 'PACKAGE.sha256', config['power_package_sha256'])
    power_inputs = json.loads((power / 'Inputs.json').read_text())
    if power_inputs.get('source_commit') != REV or Path(power_inputs['system']).resolve() != system.resolve():
        raise ValueError('Power and PR target different source/system')
    check_hashes(power_inputs['inputs'])
    power_summary = json.loads((power / 'CurrentPowerSummary.json').read_text())
    for name in ('ff1', 'encoder'):
        data = power_summary['tasks'][name]
        task = data['task']
        if task['status'] != 'CURRENT_TASK_GOLDEN_AND_ACTIVITY_PASS' or sha(power / name / 'task.saif') != task['saif_sha256']:
            raise ValueError('Power task activity not fingerprinted: ' + name)
        print('MEASURED_POWER:', name, 'system_mW=' + str(data['system_power']['total_w'] * 1000),
              'dynamic_mW=' + str(data['system_power']['dynamic_w'] * 1000),
              'leakage_mW=' + str(data['system_power']['leakage_w'] * 1000),
              'accelerator_mW=' + str(data['accelerator_power']['total_w'] * 1000),
              'cycles=' + str(task['cycles']), 'duration_s=' + str(task['duration_seconds']), flush=True)
    save(out / 'PowerEvidenceSummary.json', power_summary)
    reference_source, references, physical, physical_path = physical_references(soc)
    selection = physical['selection']
    original = dict(system_inputs['sha256'])
    original.update(power_inputs['inputs'])
    for p in [flow / 'FlowProgress.json', system / 'SystemSummary.json', system / 'SystemInputs.json',
              system / 'SystemOutputs.json', power / 'PACKAGE.sha256', power / 'Inputs.json', power / 'CurrentPowerSummary.json',
              reference_source / 'NewPrSummary.json', reference_source / 'PrRecoveryInputs.json', physical_path]:
        original[str(p)] = sha(p)
    for name, h in outputs.items():
        original[str(system / 'mapped' / name)] = h
    inputs = out / 'inputs'
    inputs.mkdir()
    for name in ('candidate.v', 'candidate.sdc'):
        source = system / 'mapped' / name
        shutil.copy2(source, inputs / name)
        if sha(inputs / name) != outputs[name]:
            raise ValueError('Current system copy mismatch: ' + name)
    period = serialized_clock((inputs / 'candidate.sdc').read_text())
    # Physical LEF coverage of every structural leaf reference, before native link.
    old_record = json.loads((reference_source / 'PrRecoveryInputs.json').read_text())
    shared_lefs = [Path(p) for p in old_record['inputs'] if Path(p).name == 'RAMSP4096X16.lef']
    if len(shared_lefs) != 1:
        raise ValueError('Expected one ledger-bound shared macro LEF')
    shared_lef = shared_lefs[0]
    lef_paths = [Path(selection['std_lef']), Path(selection['macro_lef']), shared_lef]
    infos = [lef_info(p.read_text()) for p in lef_paths]
    refs = structural_references((inputs / 'candidate.v').read_text())
    allmacros = {key: value for info in infos for key, value in info['macros'].items()}
    if not set(refs) <= set(allmacros):
        raise ValueError('Reference LEFs do not cover new logical leaves: ' + str(sorted(set(refs) - set(allmacros))))
    if not {'RAMSP1024X16', 'RAMSP4096X16'} <= set(refs):
        raise ValueError('New system must contain both macro classes')
    # Tie shared LEF to the ledger of the successfully created original shared NDM.
    if str(shared_lef) not in old_record['inputs']:
        raise ValueError('Shared LEF not in old validated physical input ledger')
    check_hashes({str(shared_lef): old_record['inputs'][str(shared_lef)]})
    power_pins, ground_pins = set(), set()
    for ref in refs:
        pins = allmacros[ref]['pins']
        if not {'POWER', 'GROUND'} <= {v['use'] for v in pins.values()}:
            raise ValueError('Physical cell lacks PG pin definition: ' + ref)
        power_pins.update(k for k, v in pins.items() if v['use'] == 'POWER')
        ground_pins.update(k for k, v in pins.items() if v['use'] == 'GROUND')
    if not power_pins <= {'VDD', 'VDDCE', 'VDDPE'} or not ground_pins <= {'VSS', 'VSSE'}:
        raise ValueError('Unreviewed logical PG pin mapping')
    for path in lef_paths + [Path(selection['technology']), Path(selection['tech_lef'])]:
        original[str(path)] = sha(path)
    ndms = []
    for label, (source, expected) in references.items():
        dest = out / ('library_' + label) / (label + '.ndm')
        dest.parent.mkdir()
        shutil.copytree(source, dest)
        if tree(dest) != expected:
            raise ValueError('Reference NDM copy differs: ' + label)
        ndms.append(dest)
    stage = out / 'design'
    stage.mkdir()
    lib = stage / 'system_707cd7f.nlib'
    cfg = ''.join(scalar(k, v) for k, v in [('PrTechnology', selection['technology']), ('PrDesignLib', lib),
        ('PrNetlist', inputs / 'candidate.v'), ('PrSdc', inputs / 'candidate.sdc'), ('PrExpectedClockPeriod', period)])
    cfg += tlist('PrRefLibs', ndms) + tlist('PrPowerPins', sorted(power_pins)) + tlist('PrGroundPins', sorted(ground_pins))
    (stage / 'CurrentConfig.tcl').write_text(cfg)
    shutil.copy2(HERE / 'PgCandidate.json', stage / 'PgCandidate.json')
    shutil.copy2(HERE / 'PgCandidate.tcl', stage / 'PgCandidate.tcl')

    record = {'source_commit': REV, 'design_source': str(system), 'system_flow': str(flow), 'power_run': str(power),
        'reference_source': str(reference_source), 'top': 'e203_cpu_top', 'inputs': original,
        'reference_snapshots': {str(p): h for p, h in references.values()},
        'design_netlist_sha256': sha(inputs / 'candidate.v'), 'design_sdc_sha256': sha(inputs / 'candidate.sdc'),
        'reference_usage': 'only copied and tree-hash checked std/private/shared NDM, TF/LEF; no old design nlib/DEF/netlist imported',
        'lef_macro_sizes': {r: allmacros[r]['size_um'] for r in ('RAMSP1024X16', 'RAMSP4096X16')},
        'expected_serialized_period_ns': period,
        'scope': 'new 707cd7f E203 system, private56/shared64; initial geometric placement only; no PG straps/RC/CTS/route/signoff'}
    save(out / 'NewPrInputs.json', record)
    icc = Path(os.environ.get('ICC2_BIN') or physical['icc2'])
    if not icc.is_file() or not os.access(str(icc), os.X_OK):
        raise ValueError('ICC2 executable unavailable: ' + str(icc))
    print('SOURCE_COMMIT:', REV, flush=True)
    print('CURRENT_DESIGN_SOURCE:', system, flush=True)
    print('CURRENT_NETLIST_SHA256:', record['design_netlist_sha256'], flush=True)
    print('REFERENCE_USAGE: checked NDM copies only; no NDM rebuild and no old design import', flush=True)
    print('CLOCK_SERIALIZATION: target6.666667ns serialized=' + period, flush=True)
    text = native(out, 'system_place', stage, icc, physical['icc2_flag'], HERE / 'Place.tcl', 3600)
    if 'NEW_SYSTEM_INITIAL_PLACEMENT_NATIVE_COMPLETE' not in text:
        raise ValueError('Native new system placement incomplete')
    for path in (lib, stage / 'initial_floorplan.def', stage / 'placed_707cd7f.def'):
        if not path.exists() or (path.is_file() and path.stat().st_size == 0):
            raise ValueError('Missing new checkpoint: ' + str(path))
    if not lib.is_dir() or not any(p.is_file() and p.stat().st_size for p in lib.rglob('*')):
        raise ValueError('Saved new design library is empty')
    for name in ('candidate.v', 'candidate.sdc'):
        if sha(inputs / name) != outputs[name]:
            raise ValueError('Native PR changed copied logical input: ' + name)
    geometry(stage, out, record['lef_macro_sizes'])
    io_summary = validate_io(stage)
    print('IO_VALIDATION:', json.dumps(io_summary, sort_keys=True), flush=True)

    verify(original)
    for source, expected in references.values():
        if tree(source) != expected:
            raise ValueError('Original reference NDM changed')
    (out / 'OpenLayout.tcl').write_text('open_lib {' + str(lib) + '}\nopen_block e203_cpu_top\nstart_gui\n')
    save(out / 'NewPrSummary.json', {'result': 'NEW_707CD7F_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING',
        'source_commit': REV, 'design_source': str(system), 'design_netlist_sha256': record['design_netlist_sha256'],
        'original_inputs_unchanged': True, 'macro_count': 120, 'macro_bbox_overlap_count': 0,
        'io_validation': io_summary, 'pg_candidate_pitch_um': 42, 'pg_compiled': False,
        'design_library': str(lib), 'placed_def': str(stage / 'placed_707cd7f.def'),
        'limitations': 'initial placement; standard-cell legalization/PG straps/RC/CTS/route/signoff not completed'})
    print('ORIGINAL_INPUTS_UNCHANGED: True', flush=True)
    print('LAYOUT_LIBRARY:', lib, flush=True)
    print('OPEN_GUI:', str(icc) + ' ' + physical['icc2_flag'] + ' ' + str(out / 'OpenLayout.tcl'), flush=True)
    print('RESULT: NEW_707CD7F_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING', flush=True)


if __name__ == '__main__':
    output = Path(sys.argv[1]).resolve()
    try:
        main(output)
    except Exception as error:
        import traceback
        print('NEW_707CD7F_PR_ERROR:', error, flush=True)
        traceback.print_exc()
        print('RESULT: NEW_707CD7F_PR_INCOMPLETE_RETAIN_CHECKPOINTS', flush=True)
        raise SystemExit(2)
    finally:
        with tarfile.open(str(output / 'InitialPrReports.tar.gz'), 'w:gz') as archive:
            for path in sorted(output.iterdir()):
                if path.name.endswith(('.tar.gz', '.ndm')) or path.name.startswith('library_') or path.name == 'runner.log':
                    continue
                # nlib stays on server; DEF and complete scripts/reports are archived separately.
                if path.name == 'design':
                    for p in path.iterdir():
                        if p.is_file():
                            archive.add(str(p), arcname='design/' + p.name)
                elif path.is_file() or path.name in ('inputs', 'tools'):
                    archive.add(str(path), arcname=path.name)
